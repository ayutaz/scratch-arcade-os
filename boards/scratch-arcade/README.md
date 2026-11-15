# 対象基板と確認範囲

設定は[profile.json](profile.json)にまとめた1台の観測値。ESP32-S3 rev0.2、Flash8MiB、LCD320×240。Maker版は写真から有力候補だが、PCB Rev/液晶部品刻印/音声ICは未確定。標準版とLITE版の互換profileではない。

| 周辺 | 観測した設定 |
|---|---|
| LCD | ST7789 backend、SCK12/MOSI11/CS10/DC45/RESET46/BL21、rotation3 |
| ボタン | FN0/A39/B5/X9/Y4、active-low/pull-up |
| ジョイスティック | ADC X6/Y8 |
| 出力 | I2S SCK41/WS42/DATA1 |
| 入力 | PDM CLK47/DATA48、16kHz/16bit/mono |
| PSRAM | チップは8MBを報告。現行profile無効、全容量/clock未検証 |

値は元の開発で得た純正設定と独自BSPの試験に基づく。回路図・物理配線の独立検証や、同名製品の全基板への互換保証ではない。profileには取得元Flashのhash・抽出コード・機器IDを含めない。

LCDの初期化コマンドと遅延もprofileに記載し、ホスト契約テストでC driverと照合する。本体や未知GPIOを走査してprofileを推測しない。
