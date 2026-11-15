from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class DatagramServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe=Path(cls.tmp.name)/'udp'
        native=ROOT/'prototypes/lab-os/native'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-I'+str(native),
             str(native/'udp_service.c'),str(ROOT/'tests/native/lab_udp_service_contract.c'),
             '-o',str(cls.exe)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
    def check(self,name):
        p=subprocess.run([str(self.exe),name],capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr)
    def test_os_route_and_exclusive_owner_are_required_before_io(self):self.check('lease')
    def test_one_owned_tx_copy_and_backpressure_preserve_exact_binary_packet(self):self.check('bounded')
    def test_rx_slot_is_not_overwritten_and_short_caller_buffer_does_not_consume_it(self):self.check('receive')
    def test_tx_deadline_wrap_fails_closed_without_more_io(self):self.check('deadline')
    def test_partial_open_and_close_failure_keep_owner_until_release_succeeds(self):self.check('partial')
    def test_release_scrubs_queued_payload_even_if_driver_cleanup_fails(self):self.check('cleanup')
    def test_oversized_packet_is_dropped_but_native_contract_and_partial_send_failures_stop_io(self):self.check('malformed')
