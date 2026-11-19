"""未割当の既定ラベルから、既知の標準Intel runnerへ明示する契約。"""
import unittest
from test_ci import load
class ExplicitMacRunnerTests(unittest.TestCase):
 def test_host_uses_the_explicit_standard_intel_label(self):
  job=load('.github/workflows/host-tests.yml')['jobs']['host']
  self.assertEqual(job['runs-on'],'macos-15-intel');self.assertEqual(job['name'],'Host tests')
 def test_target_uses_the_same_explicit_standard_intel_label(self):
  job=load('.github/workflows/host-tests.yml')['jobs']['target']
  self.assertEqual(job['runs-on'],'macos-15-intel');self.assertEqual(job['name'],'ESP32-S3 build')
