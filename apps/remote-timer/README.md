# Remote Timer

MacからUDPで開始/停止/照会/リセット。本体A開始/一時停止/再開、Xリセット、B/FN+B終了。固定peerのLRT1/LRA1要求・返信を使い、同一要求の再送では時間を巻き戻さない。

```sh
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project check apps/remote-timer
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.project run apps/remote-timer
```

Macは矢印、Z=A、R=X、X=B、F=FN。標準ウィンドウは物理音声/通信/保存backend未接続。[APIと制作手順](../../docs/development.md)。固定日本語字形はNoto由来/OFLで、付属OFL.txtの条件を維持する。
