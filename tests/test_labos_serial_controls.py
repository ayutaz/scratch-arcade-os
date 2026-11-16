from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch
from types import SimpleNamespace
import serial
from serial.tools import list_ports
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.transfer import serial_connection

class SerialControlsTests(unittest.TestCase):
    def test_native_macos_connection_does_not_deassert_dtr_while_rts_is_asserted(self):
        port='/dev/cu.native-test';device=SimpleNamespace(device=port,vid=0x303a,pid=0x1001);stream=Mock()
        def open_port():self.assertTrue(stream.dtr);self.assertTrue(stream.rts)
        stream.open.side_effect=open_port
        with patch.object(sys,'platform','darwin'),patch.object(list_ports,'comports',return_value=[device]),patch.object(serial,'Serial',return_value=stream):
            with serial_connection(port) as actual:self.assertIs(actual,stream)
        stream.close.assert_called_once()
    def test_other_platforms_and_bridge_profiles_keep_the_prior_control_state(self):
        for platform,vid,pid in (('darwin',0x10c4,0xea60),('linux',0x303a,0x1001),('win32',0x303a,0x1001)):
            with self.subTest(platform=platform):
                port='fixture-port';stream=Mock();device=SimpleNamespace(device=port,vid=vid,pid=pid)
                def open_port():self.assertFalse(stream.dtr);self.assertFalse(stream.rts)
                stream.open.side_effect=open_port
                with patch.object(sys,'platform',platform),patch.object(list_ports,'comports',return_value=[device]),patch.object(serial,'Serial',return_value=stream):
                    with serial_connection(port):pass
                stream.close.assert_called_once()
    def test_macos_discovery_failure_never_opens_an_unidentified_port(self):
        stream=Mock()
        with patch.object(sys,'platform','darwin'),patch.object(list_ports,'comports',side_effect=OSError('fixture')),patch.object(serial,'Serial',return_value=stream):
            with self.assertRaises(OSError):
                with serial_connection('fixture-port'):pass
        stream.open.assert_not_called()
