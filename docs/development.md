# 開発手順

ホストはmacOS arm64、Python3.12.13/uv、Zig0.15.2、WAMR2.4.5、Wasmtime50.0.1。targetは固定ESP-IDF v6.1/ESP32-S3。初回の準備は[README](../README.md)。

## TDDと新規アプリ

1. 目的・入力・終了・異常時の条件を決め、先に失敗する専用テストを書く。
2. [SDK header](../prototypes/lab-os/sdk/lab_os.h)で最小実装しGreenにする。
3. 同じWASM/入力を両VMで照合し、Macで有限実行/終了/資源解放を確認する。
4. packageを再buildし、版・権限・サイズ・hash・対応FWを確認する。
5. 実機配信は既存appの所有版/hashと許可範囲を確認した別工程にする。

```sh
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project new apps/my-app --id my-app --title 'My App'
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project check apps/my-app
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project run apps/my-app
```

checkは初期動作/有限入力/正常終了の最小検査。ゲームルールの専用テストを代替しない。Macの音声/通信/保存は物理backend未接続で、対応アプリはfallbackを表示する。

## API

| 権限 | API | 上限・戻り値 |
|---|---|---|
| draw=1 | rect | 正の範囲内矩形、128命令/呼出し |
| speaker=2 / microphone=4 | audio_tone/record/play/state/level/stop/position/set_gain | 最大2秒。mutation2回/query8回/呼出し。PCMをguestへ公開しない |
| network=8 | network_send/receive/state | 1〜64B、送受信合計2回/query8回/呼出し、固定peer |
| storage=16 | state_read/write/status | 8slot、read/status計8回/write1回/呼出し。1成功/0busyまたは未保存/−1失敗 |

任意file API、汎用text/blit、ASR/TTSはない。字形はアプリ内の固定矩形データ。音声の希望ゲイン0〜8倍は再生だけに作用し、出力上限に応じて実効倍率を制限する。

## ホスト試験と画像

```sh
uv run --locked python tools/test.py
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.practical_pipeline --output reports/demo-new
```

pipelineは4appを各2回buildしてbyte一致、両VMの38frame、正常終了を照合してPNG/JSONを作る。出力先は新しいディレクトリだけ。接続/配信/公開の引数はない。掲載PNGの出典はNoto Sans JP由来OFL字形と各appの描画命令。

## targetビルドと実機の境界

`labos.target build-candidate`が実機用entry、`build`が有限ROM core。成果物はbuild配下でGit対象外。buildはFlash/monitorを実行しない。

純正のBOOT/REPL・ファーム書換え・現状態の復元は、この公開source releaseの自動手順に含めない。対象基板を識別し、同一実機の全Flash二重保全・security・復元可能性・image/hash/全変更領域を確認してから別途判断する。`scripts/flash.sh`は拒否のまま。

USB app clientは`labos.transfer`。対応Lab OSのbeacon後だけ動作するが、hash/beacon/sessionは暗号認証の代替ではない。既存appを無条件に更新せず、未知ID/hash/押下/実行中は保護する運用が必要。
