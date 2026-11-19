"""未割当の既定ラベルから、既知の標準ARM64 runnerへ明示する契約。"""
import unittest
from test_ci import load
class ExplicitMacRunnerTests(unittest.TestCase):
 def test_host_uses_the_explicit_standard_arm64_label(self):
  job=load('.github/workflows/host-tests.yml')['jobs']['host']
  self.assertEqual(job['runs-on'],'macos-26');self.assertEqual(job['name'],'Host tests')
 def test_target_uses_the_same_explicit_standard_arm64_label(self):
  job=load('.github/workflows/host-tests.yml')['jobs']['target']
  self.assertEqual(job['runs-on'],'macos-26');self.assertEqual(job['name'],'ESP32-S3 build')

 def test_labels_match_the_arm64_only_bootstrap_architecture(self):
  from unittest.mock import patch
  import importlib.util
  from test_ci import ROOT
  spec=importlib.util.spec_from_file_location('explicit_runner_bootstrap',ROOT/'tools/bootstrap.py')
  bootstrap=importlib.util.module_from_spec(spec);spec.loader.exec_module(bootstrap)
  labels={'macos-15-intel':'x86_64','macos-26':'arm64'}
  for name in ('host','target'):
   label=load('.github/workflows/host-tests.yml')['jobs'][name]['runs-on']
   import tempfile
   from pathlib import Path
   with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp).resolve();binary=root/bootstrap.ZIG['path'];binary.mkdir(parents=True);(binary/'zig').touch()
    with patch.object(bootstrap.platform,'system',return_value='Darwin'),patch.object(bootstrap.platform,'machine',return_value=labels[label]),patch.object(bootstrap.subprocess,'check_output',return_value='0.15.2\n'):
     self.assertEqual(bootstrap.ensure_zig(root),binary)
