import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import test_labos_c_store as contract
from labos import resource_probe
from labos.build import build
from labos.package import encode
from labos.fs_image import create_image
from labos.transfer import TransferError


class ResourceProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native=resource_probe.native();cls.api=cls.native.__enter__();cls.addClassCleanup(cls.native.__exit__,None,None,None)
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.packages=[]
        for name in ('counter','game'):
            manifest,blob=build(name,Path(cls.tmp.name))
            cls.packages.append(encode(manifest,blob))
            if name=='counter':cls.counter_manifest,cls.counter_blob=manifest,blob
        cls.seed,_=create_image(cls.packages)
        manifest=dict(cls.counter_manifest,version='1.0.1')
        cls.update=encode(manifest,cls.counter_blob)
        cls.maximum=resource_probe.padded_package(cls.counter_manifest,cls.counter_blob,version='1.0.1',size=16384)

    def new(self,image=None,limit=262144):return resource_probe.Probe(self.api,self.seed if image is None else image,limit=limit)
    def assert_released(self):
        stats=resource_probe.metrics(self.api)
        self.assertEqual((stats['live_bytes'],stats['live_blocks'],stats['bad_frees']),(0,0,0))

    def test_maximum_transfer_measures_peak_then_runs_counter_and_releases_everything(self):
        with self.new() as p:
            p.window(limit=65536);c=p.client();c.install(self.maximum);c.close()
            self.assertEqual(p.run_counter(),1)
            stats=p.metrics();self.assertGreaterEqual(stats['peak_bytes'],32768)
            self.assertLessEqual(stats['peak_bytes'],65536);self.assertEqual(stats['failures'],0)
        self.assert_released()

    def test_low_budget_update_failure_keeps_recoverable_catalog_and_other_app(self):
        with self.new() as p:
            p.window(limit=8192);c=p.client()
            with self.assertRaises(TransferError):c.install(self.maximum)
            image=p.snapshot();self.assertGreater(p.metrics()['failures'],0)
        self.assert_released()
        with self.new(image) as p:
            self.assertIn(p.versions()['counter'],('1.0.0','1.0.1'))
            self.assertEqual(p.package('game'),self.packages[1]);self.assertEqual(p.run_counter(),1)
        self.assert_released()

    def test_each_update_allocation_failure_preserves_old_or_new_counter_and_game(self):
        with self.new() as p:
            p.window();c=p.client();c.install(self.update);operations=p.metrics()['attempts']
        self.assert_released();self.assertGreater(operations,0)
        for at in range(1,operations+1):
            with self.subTest(fail_at=at):
                with self.new() as p:
                    p.window(fail_at=at);c=p.client()
                    try:c.install(self.update)
                    except TransferError:pass
                    image=p.snapshot()
                self.assert_released()
                with self.new(image) as p:
                    self.assertIn(p.versions()['counter'],('1.0.0','1.0.1'))
                    self.assertEqual(p.package('game'),self.packages[1]);self.assertEqual(p.run_counter(),1)
                self.assert_released()
        print(f'LAB_HEAP_UPDATE_FAILURES cases={operations}')

    def test_each_collection_allocation_failure_retains_current_previous_and_game(self):
        with self.new() as p:
            c=p.client()
            for i in range(1,4):c.install(encode(dict(self.counter_manifest,version=f'1.0.{i}'),self.counter_blob))
            c.close();image=p.snapshot()
        with self.new(image) as p:
            p.window();c=p.client();result=c.collect();self.assertEqual(result['removed_files'],2)
            operations=p.metrics()['attempts']
        self.assert_released()
        for at in range(1,operations+1):
            with self.subTest(fail_at=at):
                with self.new(image) as p:
                    p.window(fail_at=at);c=p.client()
                    try:c.collect()
                    except TransferError:pass
                    saved=p.snapshot()
                self.assert_released()
                with self.new(saved) as p:
                    self.assertEqual(p.versions()['counter'],'1.0.3');self.assertEqual(p.package('game'),self.packages[1])
                    c=p.client();c.rollback('counter');c.close();self.assertEqual(p.versions()['counter'],'1.0.2')
                self.assert_released()
        print(f'LAB_HEAP_GC_FAILURES cases={operations}')

    def test_invalid_workspaces_images_and_budget_values_are_rejected(self):
        for image in (b'bad',bytes(65536)):
            with self.assertRaises(ValueError):self.new(image)
        for limit in (-1,True,262145):
            with self.assertRaises(ValueError):self.new(limit=limit)
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'link').symlink_to(folder/'elsewhere',target_is_directory=True)
            with mock.patch.object(resource_probe,'BUILD',folder/'link'),self.assertRaises(ValueError):
                with resource_probe.native():pass
        self.assert_released()

    def test_padding_is_valid_exact_size_and_does_not_change_app_contract(self):
        from labos.package import decode
        manifest,blob=decode(self.maximum)
        self.assertEqual(len(self.maximum),16384);self.assertTrue(blob.startswith(self.counter_blob))
        self.assertEqual((manifest['id'],manifest['version']),('counter','1.0.1'))
        for size in (0,True,16385):
            with self.assertRaises(ValueError):resource_probe.padded_package(self.counter_manifest,self.counter_blob,version='1.0.1',size=size)

    def test_report_separates_payload_budget_from_vm_pool_and_target_heap(self):
        report=resource_probe.run_report(api=self.api,cycles=3,allocation_failures=False)
        self.assertFalse(report['device_tested']);self.assertEqual(report['vm_pool_bytes'],196608)
        self.assertEqual(report['cycles'],3);self.assertEqual(report['cleanup']['live_bytes'],0)
        self.assertGreaterEqual(report['scenarios']['maximum_update']['peak_bytes'],32768)
        self.assertGreaterEqual(report['scenarios']['collection']['peak_bytes'],16384)
        self.assertFalse(report['budgets']['8192']['succeeded']);self.assertTrue(report['budgets']['65536']['succeeded'])
        self.assertTrue(all(row['recoverable'] for row in report['budgets'].values()))
        self.assertFalse(report['physical_heap_measured']);self.assert_released()

    def test_cli_has_finite_limits_and_prints_report_without_device_options(self):
        import io
        from contextlib import redirect_stdout
        output=io.StringIO();report={'device_tested':False,'format':'lab-os-system-heap-v1'}
        with mock.patch.object(resource_probe,'run_report',return_value=report) as run,redirect_stdout(output):
            self.assertEqual(resource_probe.main(['--cycles','2','--allocation-failures']),0)
        run.assert_called_once_with(cycles=2,allocation_failures=True);self.assertEqual(json.loads(output.getvalue()),report)
        for value in ('0','21'):
            with mock.patch.object(resource_probe,'run_report') as run,self.assertRaises(SystemExit):resource_probe.main(['--cycles',value])
            run.assert_not_called()

    def test_closed_probe_rejects_access_before_calling_native_functions(self):
        from contextlib import ExitStack
        p=self.new();p.close();p.close()
        with ExitStack() as stack:
            for name in ('lab_resource_dump','lab_resource_count','lab_resource_counter','lab_heap_window',
                         'lab_resource_poll','lab_resource_feed','lab_heap_metric'):
                stack.enter_context(mock.patch.object(self.api,name,side_effect=AssertionError('closed handle reached native code')))
            for action in (p.snapshot,p.versions,p.run_counter,p.window,p.metrics,p.client,
                           lambda:p.read(4),lambda:p.write(b'x'),lambda:p.package('counter')):
                with self.subTest(action=action),self.assertRaises(ValueError):action()
        self.assert_released()
