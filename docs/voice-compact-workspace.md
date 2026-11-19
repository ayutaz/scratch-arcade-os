# log-mel作業領域の寿命共有

2026-11-20。固定モデル/閾値や元の参照Cを変えず、OS側の作業領域を小さくする。

## 実機で見つかった制約

遅延確保版はHOMEの内部RAMを35,216B増やし、DeskのWi-Fi/通知/終了が成立した。一方、Wi-Fi使用後の最大連続領域は27,648Bで、認識context35,248Bを確保できずPetが起動しなかった。空き総量110,420Bだけでは判断できない。

通常再起動で16appと空き119,952Bへ戻った。音響試験は操作4/5・負例誤反応0/5・内部エラー0で、認識品質は未達のまま。今回の変更でその結果を合格に書き換えない。

## メモリ配置

| 段階 | 利用領域 |
|---|---|
| 特徴抽出 | 元と同じ26,672B。FFT/energy/bandsを計算 |
| 特徴出力 | 計算が終わった先頭8,452Bへ2,113 floatを保存 |
| CNN | その特徴を保持し、後方の別12,288Bで推論 |
| 終了 | 全workspace/特徴/logitを消去。所有/lease/診断の契約は維持 |

特徴出力はまだ必要なbands/pooled-energyには重ならない。durationは最後に保存し、float値の書込みに`memcpy`を使う。出力とworkspaceが同じ先頭を指す場合だけ新APIが受け付け、それ以外の重なりは拒否する。

`LabVoice`は35,248Bから26,800Bへ8,448B減る。これはホストlayoutの結果であり、新FW上のheap/断片化/音声品質の合格ではない。PCM64,000B、WASM pool、GPIO、PSRAM、Flash配置は変更しない。

## 参照との境界

[元の来歴](../components/voice/logmel-runtime-provenance.json)の5ファイルと数学tableを変更しない。新しい`logmel_compact.c/.h`はそのC実装を基に、alias検査とdurationの保存時点だけを適応したもの。演算順序・係数・重み・5閾値は維持する。v3/v4の既定処理は従来どおり。

## TDDと回帰

- 先行4契約を追加。compact source欠落と35KBの旧layout/共有領域不足でRed（実行1件、1 failure/1 setup error）。新APIの境界、5種の波形/無音、両PCM配置、外周guard、入力不変、27KB上限とCNN領域の非重複を検査。
- service/CMakeの選択契約も先行でcompactへ変更し、旧選択とsource欠落でRed（5件中1 failure/2 setup error）。
- 最小実装後4件/0.725秒、service9件/4.731秒でGreen。byte-copyへの整理後、全752件/97.054秒、skipなしで成功。
- 既存の固定3,448入力を回帰として再使用し、banked/contiguousの6,896分類で判定・順位・score・閾値が全一致。PCM/特徴/workspaceの消去と終了も確認、15.401秒。追加検証でありTDDや新しい独立最終評価とは呼ばない。

```sh
uv run --locked python -m unittest discover -s tests -p test_voice_compact_workspace.py -v
uv run --locked python -m unittest discover -s tests -p test_voice_logmel_runtime.py -v
uv run --locked python tools/test.py
```

次はS3 buildで容量/layoutを固定する。実機適用は新しいimage/hash/領域の個別許可後だけ行い、Wi-Fi使用後のPet起動/録音/終了を再試験する。合成4/5、実声未確認、初回ネットワーク終了後の保持RAMを無条件に許容するものではない。
