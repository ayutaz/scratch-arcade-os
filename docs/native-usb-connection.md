# Macのnative USB再接続

## 対象と変更

macOSかつ列挙したポートのVID/PIDが303a:1001の場合、シリアルopen前にDTR/RTSを両方Trueへ設定する。他のOSとUSB-UARTは従来のFalse/Falseを維持する。Macで列挙に失敗した場合はopenしない。

ESP32-S3のUSB Serial/JTAGは制御線の組合せでresetへ移る。MacのpySerialがopen時に各線を別々に更新するため、接続するだけで稼働中のアプリが終了する場合があった。ホスト側の設定変更であり、FW・GPIO・eFuseには変更しない。

## 検証

- 先行テスト: `uv run --locked python -m unittest discover -s tests -p test_labos_serial_controls.py -v`。
- Red: native Macの両線assertと列挙失敗時の拒否が2件失敗。他プロファイルは成功。
- Green: 最小変更後3件成功。`uv run --locked python tools/test.py`は全700件/skipなし成功（87.741秒）。文書リンクと公開境界も成功。
- 実機切分け: 同じMac/native USBとAgent Deskで両線Trueの再open後はappを保持、FalseではHOMEへ戻った。後者ではUSB_UART_CHIP_RESETを観測。識別子・生ログは公開しない。
- この結果は対象の1台とMacに限る。他のMac/bridge/OSや物理入力の保証ではない。FWの更新試験ではない。

## 根拠

- [Espressif ESP32-S3 TRM](https://documentation.espressif.com/esp32-s3_technical_reference_manual_en.pdf): USB Serial/JTAG章のDTR/RTS制御。
- [USB Serial/JTAG console](https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/api-guides/usb-serial-jtag-console.html)
- [Espressif serial reset実装](https://github.com/espressif/esp-pylib/blob/master/esp_pylib/serial_reset.py): 個別更新と一括制御の違い。CP2102C用HUPCL対策をnative USBへ流用していない。
