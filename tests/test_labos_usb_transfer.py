import ctypes as C
import struct
import unittest

import test_labos_transfer as protocol
import test_labos_lfs as fs

ROOT = protocol.ROOT
MAIN = ROOT / 'firmware/esp-idf/lab-os-core/main'
NATIVE = ROOT / 'prototypes/lab-os/native'
SOURCES = (NATIVE / 'app_transfer.c', MAIN / 'usb_transfer.c',
           ROOT / 'tests/native/lab_usb_bridge.c', MAIN / 'resource_monitor.c',
           ROOT / 'tests/native/lab_telemetry_fixture.c',
           ROOT / 'tests/native/lab_transfer_private_bridge.c')
FLAGS = ('-I' + str(MAIN), '-I' + str(ROOT / 'tests/native/resource_fixture'),
         '-I' + str(ROOT / 'tests/native/usb_fixture'))
EXTRA = protocol.TransferTests.extra_signatures | {
    'test_usb_set_installed': ([C.c_int], None),
    'test_usb_read_override': ([C.c_int], None),
    'test_usb_contract': ([], C.c_int),
}


class UsbTransferTests(protocol.TransferTests):
    """同じ17シナリオを実USB adapter＋IDF API fixture経由で再検証する。"""
    extra_sources, extra_flags, extra_signatures = SOURCES, FLAGS, EXTRA

    def setUp(self):
        self.lib.test_usb_set_installed(1)
        super().setUp()

    def emit(self, ctx, data, n):
        if getattr(self, 'reject_output', False):
            self.reject_output = False
            return False
        return super().emit(ctx, data, n)

    def raw(self, op, request, payload=b'', session=999):
        self.responses.clear()
        self.write(protocol.encode(protocol.Frame(op, session, request, payload)))
        frames = protocol.Parser().feed(bytes(self.responses))
        self.responses.clear()
        replies = [f for f in frames if (f.op, f.session, f.request) == (op, session, request)]
        for frame in frames:
            if frame not in replies:
                self.assertEqual((frame.op, frame.session, frame.request, frame.response), (1, 0, 0, True))
        self.assertEqual(len(replies), 1)
        return replies[0]

    def test_missing_or_removed_borrowed_driver_rejects_attach_and_frees_upload(self):
        self.raw(2, 1, struct.pack('<I', 123))
        self.begin(protocol.contract.package())
        self.lib.test_usb_set_installed(0)
        self.assertFalse(self.lib.test_transfer_poll(self.receiver, 10))
        self.assertFalse(self.lib.test_transfer_busy(self.receiver))
        self.assertFalse(self.lib.test_transfer_new(self.store, self.sender, None, 123))

    def test_nonblocking_read_bounded_write_and_read_failure_contract(self):
        self.client().close()
        self.assertEqual(self.lib.test_usb_contract(), 1)
        for invalid in (-1, 129):
            self.lib.test_usb_read_override(invalid)
            self.assertFalse(self.lib.test_transfer_poll(self.receiver, 10))
            self.assertFalse(self.lib.test_transfer_busy(self.receiver))
            # Only an explicit attach resumes the stopped service.
            self.receiver = self.lib.test_transfer_new(self.store, self.sender, None, 123)
            self.assertTrue(self.receiver)
            self.transfers.append(self.receiver)

    def test_tx_backpressure_preserves_commit_reply_for_exact_retry(self):
        self.raw(2, 1, struct.pack('<I', 123))
        package = protocol.contract.package()
        self.begin(package)
        self.raw(4, 3, struct.pack('<I', 0) + package)
        packet = protocol.encode(protocol.Frame(5, 999, 4, b''))
        self.reject_output = True
        self.assertFalse(self.lib.test_transfer_feed(self.receiver, packet, len(packet), 10))
        self.assertEqual(self.lib.test_status(self.store, 2), 1)
        self.assertTrue(self.lib.test_transfer_feed(self.receiver, packet, len(packet), 11))
        reply = protocol.Parser().feed(bytes(self.responses))
        self.assertEqual(len(reply), 1)
        self.assertEqual((reply[0].op, reply[0].status), (5, 0))
        self.assertEqual(self.lib.test_status(self.store, 2), 1)


class UsbConsoleGuardTests(fs.LittleFsFixture, unittest.TestCase):
    extra_sources, extra_signatures = SOURCES, EXTRA
    extra_flags = (*FLAGS, '-DCONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=1')

    def test_adapter_refuses_shared_console_instead_of_reconfiguring_it(self):
        self.assertTrue(self.connect())
        store = self.open_store()
        self.assertTrue(self.lib.test_home_start(store))
        sent = []
        sender = protocol.SEND(lambda ctx, data, n: sent.append(C.string_at(data, n)) or True)
        self.assertFalse(self.lib.test_transfer_new(store, sender, None, 123))
        self.assertEqual(sent, [])


class UsbSecondaryConsoleGuardTests(UsbConsoleGuardTests):
    # IDF 6.1 enables the secondary USB console by default; test it alone too.
    extra_flags = (*FLAGS, '-DCONFIG_ESP_CONSOLE_SECONDARY_USB_SERIAL_JTAG=1')
