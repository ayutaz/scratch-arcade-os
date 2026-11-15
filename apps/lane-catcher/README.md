# Lane Catcher

左右で落下物を受け止める。A開始/再開始、X表紙、B/FN+B終了。3missまたは15秒で結果表示。最高得点をslot0へ保存する。

```sh
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project check apps/lane-catcher
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project run apps/lane-catcher
```

Macは矢印、Z=A、R=X、X=B、F=FN。標準ウィンドウは物理音声/通信/保存backend未接続。[APIと制作手順](../../docs/development.md)。固定日本語字形はNoto由来/OFLで、付属OFL.txtの条件を維持する。
