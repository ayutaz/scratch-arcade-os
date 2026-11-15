# Voice Recorder

Aで2秒録音、Xで希望4倍再生、下で停止/消去、B/FN+B終了。未完了の録音を再生せず、PCMは本体RAMだけで保持する。

```sh
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project check apps/voice-recorder
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project run apps/voice-recorder
```

Macは矢印、Z=A、R=X、X=B、F=FN。標準ウィンドウは物理音声/通信/保存backend未接続。[APIと制作手順](../../docs/development.md)。固定日本語字形はNoto由来/OFLで、付属OFL.txtの条件を維持する。
