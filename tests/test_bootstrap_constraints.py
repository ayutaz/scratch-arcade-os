import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[1]

def bootstrap():
    spec=importlib.util.spec_from_file_location('constraints_bootstrap',ROOT/'tools/bootstrap.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

class ImmutableConstraintsTests(unittest.TestCase):
    def fixture(self,root):
        b=bootstrap();data=b'# verified original constraints\nexample<=1\n'
        info=dict(url=b.CONSTRAINTS['url'],source='firmware/esp-idf/host-tools/constraints-v6.1.txt',sha256=hashlib.sha256(data).hexdigest())
        source=root/info['source'];source.parent.mkdir(parents=True);source.write_bytes(data)
        return b,data,info,source
    def test_clean_bootstrap_uses_verified_vendored_bytes_without_network(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b,data,info,source=self.fixture(root)
            with mock.patch.object(b,'CONSTRAINTS',info),mock.patch.object(b,'download',side_effect=AssertionError('constraints must not use mutable download')) as fetch:
                cache=b.ensure_constraints(root)
                self.assertEqual(cache.read_bytes(),data);self.assertEqual(b.ensure_constraints(root),cache)
                fetch.assert_not_called();self.assertEqual(source.read_bytes(),data)
    def test_bad_missing_symlink_or_oversize_source_fails_even_with_valid_cache(self):
        for failure in ('tamper','missing','symlink','oversize'):
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
                root=Path(d);b,data,info,source=self.fixture(root)
                cache=root/'.cache/os-idf-tools/espidf.constraints.v6.1.txt';cache.parent.mkdir(parents=True);cache.write_bytes(data)
                if failure=='tamper':source.write_bytes(data+b'changed')
                elif failure=='oversize':source.write_bytes(b'x'*65537)
                else:
                    source.unlink()
                    if failure=='symlink':
                        other=root/'other.txt';other.write_bytes(data);source.symlink_to(other)
                with mock.patch.object(b,'CONSTRAINTS',info),mock.patch.object(b,'download') as fetch:
                    with self.assertRaises((ValueError,OSError)):b.ensure_constraints(root)
                    fetch.assert_not_called();self.assertEqual(cache.read_bytes(),data)
    def test_existing_bad_cache_is_rejected_without_overwriting_it(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);b,data,info,source=self.fixture(root)
            cache=root/'.cache/os-idf-tools/espidf.constraints.v6.1.txt';cache.parent.mkdir(parents=True);cache.write_bytes(b'bad')
            with mock.patch.object(b,'CONSTRAINTS',info),mock.patch.object(b,'download') as fetch:
                with self.assertRaises(ValueError):b.ensure_constraints(root)
                self.assertEqual(cache.read_bytes(),b'bad');fetch.assert_not_called()
