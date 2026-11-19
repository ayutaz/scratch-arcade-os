# 261特徴の音声ランタイム

2026-11-19。**新しいcontext-duration実装を選ぶホスト接続部分を追加した。学習モデルの実機採用は別工程。** 通常ビルドは既存の260特徴/v3モデルを使用する。

## 選択する構成

| 項目 | 通常 | 明示選択する新形式 |
|---|---|---|
| 特徴 | adaptive 260値 | 前後100msを保持する260値＋元の発話長 |
| 閾値 | 995の1値 | command0〜4の各1値 |
| 診断のmodel_revision | 3 | 4 |
| 対象外/無音の診断閾値 | 995（旧形式を維持） | 0（command用閾値なし） |
| Cの作業領域 | 5,680B | 5,680B |
| モデル | リポジトリ内の既存モデル | 外部の検証済み数値export |

固定のHP160/平均除去/peak4096、32,000samples、8bank、録音後の消去、lease/権限とWASM app APIは共通。診断の閾値は**最終結果でなく棄却前の1位クラス**に対応する。棄却されたcommandも正しく区別できる。

モデルrevisionは前処理/診断形式の識別で、具体的なFW hashや実機での品質を保証する値ではない。Pythonクライアントは3/4を受け取り、それ以外のrevision、範囲外の閾値、判定と点差の矛盾を拒否する。

## 検証済みexportの準備

[Arcade AI Petの固定処理](https://github.com/ayutaz/arcade-ai-pet/blob/727f9d663e22af125ea122928e73b83bc72045e7/docs/decision-freeze.md)で、数値からヘッダーを再生成・照合した出力を使用する。新しい学習済み重みや`decision_model.h`は、このOSリポジトリに追加していない。コードとモデルのライセンスを区別する。

`LAB_VOICE_CONTEXT_ASSETS`へ、その出力の実ディレクトリを絶対パスで指定すると、新C実装へ切り替わる。CMakeはruntime、入力契約、5つの整数閾値、ヘッダーhashと共有数学テーブルの一致をconfigure時に検査する。これは検証済みexportの取り違え防止で、CMake自体が任意のCヘッダーを数値検証する仕組みではない。

`components/voice/decision-runtime-provenance.json`に、再利用したApache-2.0の3ソースと上流commit/hashを保存している。共有する既存の前処理/型/数学テーブルは上流と同じ内容。

## 非書込みビルド

固定依存を用意した後、通常ビルドと別の出力先で構成する。以下はrepo rootから実行する例。`assets`には自分の検証済みexportの実パスを指定する。

```python
from pathlib import Path
import subprocess
from labos import target

assets = Path('.cache/my-verified-voice-export').resolve()
target.CANDIDATE_BUILD = target.ROOT / 'build/lab-os-context-candidate'
target.enforce_volatile_radio_config(target.CANDIDATE_BUILD)
target.prepare_candidate(target.CANDIDATE_BUILD)
command = target.command('build-candidate')
command[-1:-1] = ['-D', 'LAB_VOICE_CONTEXT_ASSETS=' + str(assets)]
subprocess.run(command, env=target.environment(), cwd=target.ROOT, check=True)
```

`PYTHONPATH=prototypes/lab-os uv run --locked python`から上のコードを実行する。ビルドは実機へ接続しない。実モデルは独立最終評価、S3のFlash/RAM/stack、固定imageレビューを通ってから適用可否を判断する。

## TDDとホスト検証

8契約を先行追加。未実装のCソース/来歴の欠落、クライアントのrevision4拒否、CMakeが新形式を選ばず不正assetも拒否しないことをRedで確認した。最終Redは5テスト実行＋serviceのsetup失敗、7失敗/3エラー。最小実装後、8件/4.875秒が成功。

```sh
uv run --locked python -m unittest discover -s tests -p test_voice_context_runtime.py -v
uv run --locked python tools/test.py
```

新しい学習モデルを使わず、発話長だけを見る人工的な1-neuron fixtureで実Cを実行した。261番目の値が4ならclass0のlogit4096、class6は3120、点差976<閾値977でunknownへ棄却する。連続/8bankの両方で同じ結果、正しい診断値、完了録音の1回消費、PCM/特徴/logit消去、権限/leaseを確認した。無音はclass6、command閾値なしを報告する。

CMakeの通常/新形式の選択、不完全metadata/型/寸法/変更ヘッダー/数学テーブル差異の拒否は、実際のconfigureを実行して検査した。ホストCのfixture成功を認識品質・S3性能・実機動作へ広げない。

全体回帰は731件/149.321秒、skipなしで成功。既存v3の固定モデル/995閾値/診断/録音消去の契約も維持した。uv lock・ローカル文書参照・公開境界検査も成功。新形式を選んだS3ビルドや学習モデルの実機適用は、このホスト記録には含まない。
