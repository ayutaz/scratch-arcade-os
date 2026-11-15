# Focus Timer

上下で10〜300秒、A開始/一時停止/再開、X設定値へ戻す、B/FN+B終了。開始時だけ設定秒数をslot0へ保存し、完了時に短い音を要求する。

```sh
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project check apps/focus-timer
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project run apps/focus-timer
```

Macは矢印、Z=A、R=X、X=B、F=FN。標準ウィンドウは物理音声/通信/保存backend未接続。[APIと制作手順](../../docs/development.md)。固定日本語字形はNoto由来/OFLで、付属OFL.txtの条件を維持する。
