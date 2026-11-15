from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
class BoardWifiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);cls.exe=Path(cls.tmp.name)/'wifi'
        main=ROOT/'firmware/esp-idf/lab-os-core/main'
        p=subprocess.run(['/usr/bin/clang','-std=c11','-Wall','-Wextra','-Werror','-I'+str(ROOT/'tests/native/wifi_fixture'),
            '-I'+str(main),str(main/'board_wifi.c'),str(ROOT/'tests/native/lab_wifi_contract.c'),'-o',str(cls.exe)],capture_output=True,text=True,timeout=30)
        if p.returncode:raise RuntimeError(p.stderr)
    def check(self,name):
        p=subprocess.run([str(self.exe),name],capture_output=True,text=True,timeout=5);self.assertEqual(p.returncode,0,p.stderr)
    def test_invalid_credentials_perform_no_sdk_calls(self):self.check('invalid')
    def test_foreign_wifi_or_default_interface_is_never_modified(self):self.check('foreign')
    def test_ram_only_config_and_own_ip_notification_without_credential_retention(self):self.check('ram')
    def test_deadline_wrap_and_late_ip_cannot_revive_failed_session(self):self.check('timeout')
    def test_disconnect_retries_are_backed_off_and_bounded(self):self.check('reconnect')
    def test_each_partial_initialization_failure_releases_only_owned_resources(self):self.check('partial')
    def test_failed_stop_retains_context_and_ignores_events_until_retry(self):self.check('stop-fail')
    def test_failed_handler_release_keeps_driver_and_retries_only_remaining_handle(self):self.check('handlers')
    def test_ambiguous_sdk_detach_failure_never_retries_a_potentially_freed_driver(self):self.check('detach-fail')
    def test_shared_default_loop_is_retained_across_repeated_sessions(self):self.check('borrow-loop')
    def test_lost_ip_releases_ready_status_and_late_events_cannot_revive_it(self):self.check('lost-ip')
    def test_unexpected_station_stop_fails_closed_without_connecting_a_stopped_driver(self):self.check('stopped')
    def test_deinit_failure_preserves_driver_and_interface_until_retry(self):self.check('deinit-fail')
    def test_connect_api_errors_also_obey_the_backoff_and_retry_limit(self):self.check('connect-fail')
    def test_cold_boot_initializes_tcpip_before_querying_default_netif(self):self.check('cold-netif')
