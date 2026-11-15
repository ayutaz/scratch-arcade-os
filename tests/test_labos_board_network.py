from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]

class BoardNetworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe=Path(cls.tmp.name)/'network'
        main=ROOT/'firmware/esp-idf/lab-os-core/main'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror',
            '-I'+str(ROOT/'tests/native/wifi_fixture'),'-I'+str(main),
            '-I'+str(ROOT/'prototypes/lab-os/native'),
            '-I'+str(ROOT/'tests/native/udp_fixture'),
            '-I'+str(ROOT/'downloads/os-research/wamr-upstream/core/iwasm/include'),
            str(main/'board_wifi.c'),str(main/'board_network.c'),
            str(main/'board_udp.c'),str(ROOT/'prototypes/lab-os/native/udp_service.c'),
            str(ROOT/'prototypes/lab-os/native/network_binding.c'),
            str(ROOT/'tests/native/lab_board_network_contract.c'),'-o',str(cls.exe)],
            capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
    def check(self,name):
        p=subprocess.run([str(self.exe),name],capture_output=True,text=True,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr)
    def test_factory_and_cold_close_do_not_initialize_radio_or_sdk(self):self.check('lazy')
    def test_wire_start_status_stop_uses_real_driver_and_refuses_reconfiguration(self):self.check('roundtrip')
    def test_timeout_releases_radio_and_interface_but_keeps_failed_status_until_restart(self):self.check('timeout')
    def test_failed_cleanup_retains_manager_until_poll_retry_finishes(self):self.check('cleanup')
    def test_invalid_or_uninitialized_requests_never_reach_sdk(self):self.check('invalid')
    def test_partial_start_failure_releases_radio_and_allows_an_explicit_new_start(self):self.check('failed-open')
    def test_route_is_ram_only_and_app_socket_requires_wifi_ready(self):self.check('route')
    def test_borrowed_app_blocks_route_radio_changes_and_parent_close(self):self.check('borrowed')
    def test_lost_link_closes_udp_before_wifi_but_retains_app_borrow_guard(self):self.check('lost-link')
    def test_failed_udp_cleanup_keeps_wifi_until_socket_release_finishes(self):self.check('udp-cleanup')
    def test_close_and_reinit_clear_route_without_any_radio_initialization(self):self.check('reinit')
