"""AI制作後のhost検証pipeline。接続/転送を含めない。"""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos import practical_pipeline as tool


class PipelineTests(unittest.TestCase):
    def test_existing_or_symlink_output_is_rejected_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp).resolve();(base/'existing').mkdir();(base/'alias').symlink_to(base/'existing',target_is_directory=True)
            for name in ('existing','alias'):
                with mock.patch.object(tool,'build_project') as build,self.assertRaises(ValueError):tool.run(base/name)
                build.assert_not_called()
    def test_failed_validation_does_not_create_ready_report_or_screens(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp).resolve()/'report'
            with mock.patch.object(tool,'verify',side_effect=ValueError('VM mismatch')),self.assertRaises(ValueError):tool.run(out)
            self.assertFalse(out.exists())
    def test_all_four_real_apps_are_rebuilt_compared_and_packaged_with_host_only_screens(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp).resolve()/'report';result=tool.run(out)
            self.assertEqual(set(result['apps']),{'lane-catcher','focus-timer','voice-recorder','remote-timer'})
            self.assertFalse(result['device_tested']);self.assertFalse(result['deployed']);self.assertFalse(result['published'])
            self.assertEqual(json.loads((out/'result.json').read_text()),result)
            for name,row in result['apps'].items():
                self.assertTrue(row['deterministic_build']);self.assertTrue(row['both_vms_match']);self.assertTrue(row['normal_exit'])
                self.assertLessEqual(row['package_bytes'],16384);self.assertGreater(row['frames'],5)
                with Image.open(out/row['screen']) as image:self.assertEqual(image.size,(320,240));self.assertGreater(len(image.getcolors(320*240)),1)
