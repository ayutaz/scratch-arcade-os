# Scratch Arcade OS

[![Host tests](https://github.com/ayutaz/scratch-arcade-os/actions/workflows/host-tests.yml/badge.svg)](https://github.com/ayutaz/scratch-arcade-os/actions/workflows/host-tests.yml)

ESP32-S3向けの、日本語ホームと後付けアプリを持つ小型OSです。ESP-IDF/FreeRTOSとWAMRを使い、ゲームやツールをC99→WebAssemblyで追加します。

**OS全体を再ビルドせずに、アプリを追加・個別更新できます。** Mac上で同じWASMを検証し、本体ではボタン操作・描画・音声・設定保存・UDP通信を共通APIから扱います。

![Mac上で同じWASMから描画したLane Catcher](docs/images/host-lane-catcher.png)

画像はMac上の描画で、実機の撮影ではありません。独立した実験プロジェクトであり、Scratch Arcadeの公式ファームウェアではありません。

## 機能

| 分野 | 実装 |
|---|---|
| ホーム | 固定日本語、アプリ選択・起動・終了、前面1本 |
| Runtime | WAMR fast interpreter、命令数/bounds/権限/API回数の上限 |
| アプリ管理 | USB転送、SHA-256/ABI検査、個別更新・旧版・削除・GC |
| 描画/入力 | 320×240 RGB565の行描画、矩形API、押下/保持/解放・実時間 |
| 音声 | 診断音、最大2秒のRAM録音/再生、進捗、再生ゲイン |
| 保存 | アプリごとの8×int32、交互CRC記録、通常再起動後の保持 |
| 通信 | OS管理のWi-Fi STA/固定UDP peer、Mac連携タイマー |
| 開発 | Wasmtime/WAMR比較、ホストAPI fixture、Macウィンドウ、TDD |

元の実機開発で11本の起動/終了、スコア/設定の再起動保持、Wi-Fi停止後の2秒録再を確認しました。今回切り出したソースの再ビルド品を実機へ再書込みしたものではありません。[検証範囲](docs/validation.md)。

## Macで試す

現在のホストツールは**macOS arm64、Python3.12.13、uv**を対象にしています。

```sh
git clone https://github.com/ayutaz/scratch-arcade-os.git
cd scratch-arcade-os
uv sync --locked
uv run --locked python tools/bootstrap.py --font
uv run --locked python tools/test.py
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project check apps/lane-catcher
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project run apps/lane-catcher
```

bootstrapは固定commitのWAMR/littlefs、checksum付きZig、指定時のフォントを取得します。既存依存の版や内容が違えば上書きせず停止します。実機には接続しません。

Macの操作は矢印、Z=A、R=X、X=B、F+X=FN+B。標準ウィンドウの音声/通信/保存backendは未接続なので、対応APIの未接続表示は想定内です。ESP32の速度・実LCD・音質のエミュレーターではありません。

## 付属アプリ

| アプリ | 内容 |
|---|---|
| [Maze Runner](apps/maze-runner/README.md) | 壁を迂回して目標を集める |
| [Audio Desk](apps/audio-desk/README.md) | 診断音・500ms録音/再生・ゲイン |
| [Lane Catcher](apps/lane-catcher/README.md) | 3レーンゲーム・最高得点保存 |
| [Focus Timer](apps/focus-timer/README.md) | 10〜300秒タイマー・設定保存 |
| [Voice Recorder](apps/voice-recorder/README.md) | RAM内2秒録音/再生 |
| [Remote Timer](apps/remote-timer/README.md) | Macから開始・停止・照会 |

SDKの基本5本（counter/game/microphone/network/speaker）も収録しています。新規ビルドのseedはgame/counterの2本で、11本を初期インストールしたimageではありません。

## ESP32-S3ビルド

```sh
uv run --locked python tools/bootstrap.py --idf
uv sync --project firmware/esp-idf/host-tools --locked
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.target build-candidate
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.target size-candidate
```

これはビルド専用です。対応は観測した1台のScratch Arcade系S3基板の設定に限ります。Maker/LITEやPCB Rev全般への互換性、既存データを保った移行は保証していません。[基板設定](boards/scratch-arcade/README.md)・[ビルド/導入の境界](docs/development.md)。`scripts/flash.sh`は常に拒否し、純正復元imageや実機固有の配備ツールは含めません。

## 構成

| 場所 | 内容 |
|---|---|
| `prototypes/lab-os/native/` | OS共通Cサービス、VM、Home、FS、USB protocol |
| `prototypes/lab-os/sdk/` | C99 SDK・基本5アプリ |
| `prototypes/lab-os/labos/` | Macツール、ビルダー、両VM、転送client |
| `firmware/esp-idf/` | 実機用candidate、有限core、共有BSP、分離uv |
| `boards/scratch-arcade/` | 対象を限定した設定と未確認事項 |
| `apps/` / `tests/` | 追加6アプリとホスト契約/異常系試験 |
| `tools/` | 固定依存取得、skipを拒否する試験runner、公開境界検査 |

[SDKと制作手順](docs/development.md)・[アーキテクチャ](docs/architecture.md)・[検証](docs/validation.md)・[依存](docs/dependencies.md)。

## ライセンス

自作コードは[Apache-2.0](LICENSE)。第三者コード・MicroPython由来ASCIIフォント・Noto由来字形は、それぞれのライセンスを維持します。[NOTICE](NOTICE)・[第三者の権利表示](THIRD_PARTY_NOTICES.md)。

純正ファームウェア、抽出コード、Flash原本、録音、Wi-Fi認証情報、個人の実機識別子は配布しません。OS OTA、任意nativeアプリの完全隔離、任意の日本語文字入力、BLE、ASR/TTSは未実装/未検証の範囲です。
