import ctypes as C
import hashlib
import unittest

import test_labos_c_store as contract
from test_labos_lfs import LittleFsFixture, ROOT


class GarbageCollectionTests(LittleFsFixture, unittest.TestCase):
    extra_sources = (ROOT / 'tests/native/lab_gc_bridge.c',)
    extra_signatures = {
        'test_gc_new': ([], C.c_void_p), 'test_gc_free': ([C.c_void_p], None),
        'test_gc_begin': ([C.c_void_p] * 3, C.c_int), 'test_gc_step': ([C.c_void_p], C.c_int),
        'test_gc_close': ([C.c_void_p], C.c_int), 'test_gc_stat': ([C.c_void_p, C.c_int], C.c_uint32),
        'test_gc_store_close': ([C.c_void_p], C.c_int), 'test_gc_blocks': ([C.c_void_p], C.c_int),
        'test_gc_store_reinit': ([C.c_void_p], C.c_int),
        'test_action': ([C.c_void_p, C.c_char_p, C.c_int], C.c_int),
        'test_open': ([C.c_void_p, C.c_char_p], C.c_int), 'test_release': ([C.c_void_p], None),
    }

    def setUp(self):
        super().setUp();self.assertTrue(self.connect());self.store = self.open_store()
        self.gc = self.lib.test_gc_new();self.addCleanup(self.lib.test_gc_free, self.gc)

    def blob_path(self, pack): return '/lab-apps/' + hashlib.sha256(pack).hexdigest() + '.lab'
    def put(self, path, data): self.assertTrue(self.lib.test_lfs_raw_put(self.volume, path.encode(), data, len(data)))
    def begin(self): self.assertTrue(self.lib.test_gc_begin(self.gc, self.volume, self.store))
    def finish(self):
        for i in range(4096):
            result = self.lib.test_gc_step(self.gc)
            if result != 0: return result
        self.fail('collector did not finish in bounded fixture')
    def collect(self): self.begin();self.assertEqual(self.finish(), 1)
    def stats(self): return [self.lib.test_gc_stat(self.gc, i) for i in range(4)]
    def versions(self, count=4):
        packs = [contract.package(value=i, version=f'1.0.{i}') for i in range(count)]
        for p in packs: self.assertTrue(self.install(self.store, p))
        return packs
    def fresh_store(self, image):
        self.volume = self.new_volume(image, format=False);self.assertTrue(self.connect(create=False));return self.open_store()

    def test_no_orphans_is_no_write_and_does_not_advance_sequence(self):
        self.versions(2);before=self.snapshot();seq=self.lib.test_status(self.store, 2)
        self.collect()
        self.assertEqual(self.snapshot(), before);self.assertEqual(self.stats()[:2], [0, 0])
        self.assertEqual(self.lib.test_status(self.store, 2), seq)
        self.assertEqual(self.lib.test_gc_step(self.gc), 1)

    def test_zero_hash_previous_marker_does_not_keep_a_zero_named_orphan(self):
        self.versions(1);path='/lab-apps/'+'0'*64+'.lab';self.put(path,b'not-a-previous-version')
        self.collect();self.assertIsNone(self.raw_get(path));self.assertEqual(self.stats()[0],1)

    def test_old_versions_collected_after_checkpoint_keep_current_previous_and_other_app(self):
        packs=self.versions();game=contract.package('game');self.assertTrue(self.install(self.store, game))
        owner=self.raw_get('/lab-apps/owner');seq=self.lib.test_status(self.store, 2)
        self.collect()
        for p in packs[:2]: self.assertIsNone(self.raw_get(self.blob_path(p)))
        for p in packs[2:]+[game]: self.assertEqual(self.raw_get(self.blob_path(p)), p)
        self.assertEqual(self.raw_get('/lab-apps/owner'), owner)
        self.assertEqual(self.stats()[:2], [2, sum(map(len,packs[:2]))])
        self.assertEqual(self.lib.test_status(self.store,2),seq+1)
        self.assertEqual(self.stats()[2]-self.stats()[3], self.stats()[1])
        self.assertTrue(self.lib.test_action(self.store,b'counter',0));self.assertEqual(self.version(self.store), '1.0.2')

    def test_uninstall_collects_package_and_both_index_fallbacks_stay_valid(self):
        p=contract.package();self.assertTrue(self.install(self.store,p))
        self.assertTrue(self.install(self.store,contract.package('game')))
        self.assertTrue(self.lib.test_action(self.store,b'counter',1));self.collect()
        self.assertIsNone(self.raw_get(self.blob_path(p)))
        image=self.snapshot()
        for slot in (0,1):
            self.fresh_store(image);self.put(f'/lab-apps/index-{slot}', b'torn')
            reopened=self.open_store();self.assertEqual(self.lib.test_count(reopened),1)
            self.assertEqual(self.version(reopened),'1.0.0')

    def test_live_lease_other_collector_mutations_open_and_store_close_are_rejected(self):
        self.versions();self.assertTrue(self.lib.test_open(self.store,b'counter'))
        self.assertFalse(self.lib.test_gc_begin(self.gc,self.volume,self.store));self.lib.test_release(self.store)
        self.begin();other=self.lib.test_gc_new()
        try: self.assertFalse(self.lib.test_gc_begin(other,self.volume,self.store))
        finally: self.lib.test_gc_free(other)
        self.assertFalse(self.install(self.store,contract.package('game')))
        self.assertFalse(self.lib.test_action(self.store,b'counter',1))
        self.assertFalse(self.lib.test_open(self.store,b'counter'))
        self.assertFalse(self.lib.test_gc_store_close(self.store))
        self.assertTrue(self.lib.test_gc_close(self.gc));self.assertTrue(self.lib.test_gc_close(self.gc))
        self.assertTrue(self.lib.test_open(self.store,b'counter'));self.lib.test_release(self.store)

    def test_foreign_store_cannot_collect_this_volume(self):
        self.versions();saved=self.volume
        self.volume=self.new_volume();self.assertTrue(self.connect());foreign=self.open_store();self.volume=saved
        before=self.snapshot();self.assertFalse(self.lib.test_gc_begin(self.gc,self.volume,foreign));self.assertEqual(self.snapshot(),before)

    def test_reinitializing_adapter_or_store_cannot_bypass_collection_ownership(self):
        self.versions();self.begin();before=self.snapshot()
        with self.subTest(adapter=True): self.assertFalse(self.connect(create=False))
        with self.subTest(store=True): self.assertFalse(self.lib.test_gc_store_reinit(self.store))
        self.assertFalse(self.install(self.store,contract.package('game')))
        self.assertEqual(self.snapshot(),before);self.assertEqual(self.finish(),1)

    def test_unknown_names_or_directories_are_detected_before_any_write(self):
        packs=self.versions();baseline=self.snapshot()
        for kind in ('file','directory'):
            self.store=self.fresh_store(baseline)
            if kind=='file': self.put('/lab-apps/z-foreign',b'keep')
            else: self.assertEqual(self.lib.test_lfs_mkdir(self.volume,b'/lab-apps/z-foreign'),0)
            before=self.snapshot();self.begin();self.assertEqual(self.finish(),-1);self.assertEqual(self.snapshot(),before)
            for p in packs: self.assertEqual(self.raw_get(self.blob_path(p)),p)

    def test_owner_or_referenced_package_corruption_blocks_checkpoint_and_deletion(self):
        packs=self.versions();baseline=self.snapshot()
        for path in ('/lab-apps/owner',self.blob_path(packs[-1]),self.blob_path(packs[-2])):
            self.store=self.fresh_store(baseline);self.put(path,b'broken');before=self.snapshot()
            if self.lib.test_gc_begin(self.gc,self.volume,self.store): self.assertEqual(self.finish(),-1)
            self.assertEqual(self.snapshot(),before)
            self.assertEqual(self.raw_get(self.blob_path(packs[0])),packs[0])

    def test_changed_catalog_is_not_checkpointed_over_a_newer_external_snapshot(self):
        self.versions();other=self.open_store();self.assertTrue(self.install(other,contract.package('game')))
        before=self.snapshot();self.begin();self.assertEqual(self.finish(),-1);self.assertEqual(self.snapshot(),before)

    def test_empty_store_orphan_is_removed_only_after_two_empty_snapshots_exist(self):
        self.put('/lab-apps/'+'a'*64+'.lab',b'partial')
        self.collect();self.assertEqual(self.stats()[:2],[1,7]);self.assertEqual(self.lib.test_count(self.store),0)
        self.assertEqual(len(self.raw_get('/lab-apps/index-0')),1728);self.assertEqual(len(self.raw_get('/lab-apps/index-1')),1728)
        self.assertEqual(self.stats()[3],len(b'lab-os-c-store-v1\n')+3456)

    def test_one_step_removes_at_most_one_blob_and_cancellation_preserves_live_apps(self):
        self.versions(10);self.begin();previous=0
        for _ in range(200):
            self.assertEqual(self.lib.test_gc_step(self.gc),0)
            removed=self.stats()[0];self.assertLessEqual(removed-previous,1);previous=removed
            if removed: break
        else: self.fail('no garbage removed')
        self.assertTrue(self.lib.test_gc_close(self.gc))
        reopened=self.fresh_store(self.snapshot());self.assertEqual(self.version(reopened),'1.0.9')
        self.assertTrue(self.lib.test_action(reopened,b'counter',0));self.assertEqual(self.version(reopened),'1.0.8')

    def test_adjacent_orphans_are_not_skipped_and_data_blocks_can_be_reused(self):
        packs=self.versions();extra=[]
        for i in range(10):
            p=bytes([i])*32768;path='/lab-apps/'+hashlib.sha256(p).hexdigest()+'.lab';extra.append(path);self.put(path,p)
        before=self.lib.test_gc_blocks(self.volume);self.collect()
        self.assertEqual(self.stats()[0],12)
        self.assertLess(self.lib.test_gc_blocks(self.volume),before)
        for path in extra: self.assertIsNone(self.raw_get(path))
        self.put('/lab-apps/'+'e'*64+'.lab',b'x'*65536)
        self.assertEqual(self.raw_get(self.blob_path(packs[-1])),packs[-1])

    def test_full_logical_quota_can_recover_capacity_and_install_another_app(self):
        packs=[contract.package(value=i,version=f'1.0.{i}') for i in range(4)]
        self.assertTrue(self.connect(quota=len(b'lab-os-c-store-v1\n')+3456+sum(map(len,packs))))
        for p in packs: self.assertTrue(self.install(self.store,p))
        self.assertFalse(self.install(self.store,contract.package('game')))
        self.assertFalse(self.lib.test_gc_begin(self.gc,self.volume,self.store))
        self.store=self.open_store();self.collect()
        self.assertTrue(self.install(self.store,contract.package('game')))

    def test_namespace_limit_reserves_checkpoint_slots_and_rejects_excess_before_writes(self):
        self.versions(1)
        for i in range(1021): self.put('/lab-apps/'+f'{i:064x}'+'.lab',b'x')
        baseline=self.snapshot();self.collect();self.assertEqual(self.stats()[0],1021)
        self.assertEqual(self.version(self.store),'1.0.0')
        self.store=self.fresh_store(baseline);self.put('/lab-apps/'+'f'*64+'.lab',b'x')
        before=self.snapshot();self.begin();self.assertEqual(self.finish(),-1)
        self.assertEqual(self.snapshot(),before)

    def test_every_write_cut_preserves_current_previous_and_other_app_after_remount(self):
        self.versions();game=contract.package('game');self.assertTrue(self.install(self.store,game));baseline=self.snapshot()
        self.lib.test_lfs_cut(self.volume,1000000,False);self.collect();operations=self.lib.test_lfs_operations(self.volume)
        self.assertGreater(operations,0)
        for partial in (False,True):
            for at in range(operations+1):
                with self.subTest(cut=at,partial=partial):
                    self.store=self.fresh_store(baseline);self.lib.test_lfs_cut(self.volume,at,partial)
                    self.begin();self.finish();self.assertTrue(self.lib.test_gc_close(self.gc))
                    reopened=self.fresh_store(self.snapshot());self.assertEqual(self.version(reopened),'1.0.3')
                    self.assertEqual(self.raw_get(self.blob_path(game)),game)
                    self.assertTrue(self.lib.test_action(reopened,b'counter',0));self.assertEqual(self.version(reopened),'1.0.2')
        type(self).cut_summary={'operations':operations,'cases':2*(operations+1)}
        print(f'LAB_GC_CUTS operations={operations} cases={2*(operations+1)}')


if __name__=='__main__': unittest.main()
