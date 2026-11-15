# Audio Desk

左右で診断音/500ms録音/再生を選び、A実行。上下で希望ゲイン1/2/4/8倍、X停止/消去、B/FN+B終了。PCMは本体RAMだけに置く。

```sh
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project check apps/audio-desk
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project run apps/audio-desk
```

Macは矢印、Z=A、R=X、X=B、F=FN。標準ウィンドウは物理音声/通信/保存backend未接続。[APIと制作手順](../../docs/development.md)。日本語Homeの字形と、各アプリのコード/描画内容は別に管理する。
