# Maze Runner

30秒以内に壁を迂回し、黄色の目標を3個集める。方向で移動、A開始/再開始、X表紙、B/FN+B終了。

```sh
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project check apps/maze-runner
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project run apps/maze-runner
```

Macは矢印、Z=A、R=X、X=B、F=FN。標準ウィンドウは物理音声/通信/保存backend未接続。[APIと制作手順](../../docs/development.md)。日本語Homeの字形と、各アプリのコード/描画内容は別に管理する。
