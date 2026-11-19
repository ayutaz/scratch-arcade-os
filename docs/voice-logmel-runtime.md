# 明示選択のlog-mel CNN音声処理

既定は既存v3。`LAB_VOICE_LOGMEL_ASSETS`に別途検証した数値exportの実パスを渡す場合だけ、2,113特徴/6層CNN/5閾値を使う。261特徴の指定とは併用できない。

- 録音の所有・権限・完了条件、HP160/level、PCM消去と終了解放は共通。
- 診断はmodel_revision5と、その1位classに対応する閾値を返す。guest APIのschemaは変えない。
- 特徴抽出26,672Bと推論12,288Bは同じworkspaceを順に再利用。features2,113値と診断を含むLabVoiceは36,000B以下。
- 数値header/数学table/weights hash/入力契約をCMakeで検査。数学tableは同梱の固定sourceと一致が必要。
- CMakeによる検査はtrusted producerの数値export向けであり、悪意あるC source/headerをsandboxで実行するものではない。

```sh
# Existing candidate-build environment; this does not flash a device.
# Pass the separately verified numeric export when configuring ESP-IDF:
idf.py -D LAB_VOICE_LOGMEL_ASSETS=/absolute/path/to/verified/export build
```

## 検証

先行8契約を追加し、source/table/来歴の欠落・revision5拒否・選択不足でRed（5test実行/5error、service setup失敗を含む）。実装後8件/6.621秒でGreen。全体739件/132.200秒、skipなし。

既存の「未知revision5拒否」の試験は、新対応に合わせ未知revision6へ変更した。新しい試験でもrevision6・閾値4097・負例の非0閾値を拒否し、v3/v4の規則は維持する。実Cの両PCM layout、消去、lease/権限、終了後診断無効化を確認した。試験のCNNはdurationだけを使う人工fixtureで、実モデル品質の検証ではない。

C/header4本と数学tableは[固定来歴](../components/voice/logmel-runtime-provenance.json)に記録する。学習した重みは本repoへ追加しない。host成功を、S3での速度/heap/録音品質や実声認識の合格と扱わない。別の固定imageへの実機更新には個別レビュー/許可が必要。
