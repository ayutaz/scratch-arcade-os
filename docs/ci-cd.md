# CI/CDとmain保護

2026-11-16 JST。ホスト・target build・実機の結果を区別する。CIはUSBへ接続せず、Flashを変更しない。

## 必須チェック

| チェック名 | 内容 | 環境 |
|---|---|---|
| Repository checks | 両uv lock、CI契約、actionlint、Markdown参照、公開対象の秘密/生成物検査 | Ubuntu 24.04 |
| Host tests | 固定公開依存を新規取得し、全ホスト試験。skipも失敗扱い | macOS 15 arm64 |
| ESP32-S3 build | 固定ESP-IDF/ツールチェーン取得、candidate buildとsize | macOS 15 arm64 |
| Dependency audit | 両lockをexportし、pip-auditで既知のPython脆弱性を照合 | Ubuntu 24.04 |

全PR、mainへのpush、手動、毎週月曜UTC 04:23に実行する。必須jobにpath除外や成功扱いのskipを使わない。PRの古い実行は後続pushで取り消す。host log・size・監査JSONだけを14日間保存し、firmware binaryはアップロードしない。

Actionsはcommit SHA、uvは0.11.23、pip-auditは2.10.1に固定。Python/アプリ依存は各uv.lockに従う。PRはcontents:read、checkoutの資格情報を残さず、pull_request_targetを使わない。依存cacheを共有せず、初回導入の再現も検査する。

Dependabotは毎週、root/IDFのuvとActionsの更新PRを作る。Zig/WAMR/littlefs/IDF/フォントの固定値は自動変更せず、互換性・license・容量を確認して更新する。Python監査はC依存やESP-IDF全体の脆弱性を保証しない。

## mainの保護

設定の正本は[main-protection.json](../.github/main-protection.json)。変更は管理APIで適用し、GETで実設定を確認する。

- PR経由の更新、上表4チェックの成功、最新mainへの追従を必須にする。
- 必須checkはGitHub Actions appに限定し、管理者にも保護を適用する。
- 未解決のreview conversationを残したmerge、force push、branch削除を拒否する。
- 一人での開発を止めないよう、他者の承認件数は0。人のレビューを通過したという意味ではない。

```sh
gh api --method PUT repos/ayutaz/scratch-arcade-os/branches/main/protection \
  --input .github/main-protection.json
gh api repos/ayutaz/scratch-arcade-os/branches/main/protection
```

通常の開発はbranch→先行Red→実装/Green→commit/push→PR→CI成功→merge。失敗したcheckを無視するadmin mergeは使わない。

## ソース配布

`vMAJOR.MINOR.PATCH`タグのpushで、同じ4チェックを再実行する。成功後、mainに含まれるcommit・pyproject.tomlとの版一致・cleanなcheckout・公開境界を再確認して、source.tar.gzとSHA256SUMSをGitHub Releaseへ登録する。

[配布ツール](../tools/source_release.py)はGitの追跡sourceだけをarchive化し、同一commitのgzip timestampを固定する。既存出力/既存Releaseは上書きしない。通常PRの権限は読み取りのみで、タグ配布のpublish jobだけcontents:writeを持つ。

新しいRelease作成前には版と配布対象を確認する。今回タグ/Releaseは作らず、配布処理はfixtureのローカルテストで検証する。これは実機へのCD/OTAでも、復元可能なfirmware binaryの配布でもない。

## ローカル検証

```sh
uv sync --locked
uv run --locked python -m unittest discover -s tests -p 'test_ci*.py' -v
uv run --locked python tools/check_repository.py
uv run --locked python tools/publication_check.py
uv run --locked python tools/bootstrap.py --font
uv run --locked python tools/test.py
```

新規ファイルの公開境界はstage後の追跡集合で確認する。テスト/実装に未コミット変更がある間、source_release.pyは拒否する。

## 実装記録

12契約を先に追加し、未実装のworkflow/保護設定/二言語README/検査・配布ツールで意図したRed（1 failure/11 errors）を確認した。実装後、fixtureのmacOS /varと/private/varの別名問題を正規化して12件Green。さらにIDFの監査修正2件、checksum付きactionlint実行1件も各先行Red→Greenとし、計15件成功。このfixture修正自体を機能のRedとは数えない。

配布テストはdirty tree・版不一致・別commitのtag・追跡binary・出力上書き・symlinkを拒否し、同じsourceのarchive byte一致とSHA-256を確認する。Markdown検査は欠落file/見出し・repo外への参照を拒否する。

ローカルの追加契約は15件/skipなし成功。actionlint1.7.12（公式release digest照合）も成功。Python監査は最初IDFのcryptography48.0.1で失敗し、50.0.2へ更新して両lockとも検出0となった。[self-managed依存の理由](dependencies.md#idfのpython依存の保守)。公式idf_toolsの必要/推移依存チェックも成功し、S3ビルド910,368Bが成功した。今回の実機操作はない。

全体ホスト試験は690件/skipなし成功（85.793秒。後続のactionlint契約1件は追加契約15件のGreenで確認）。main保護はAPIで実適用し、4check/app_id15368/strict、管理者適用、PR必須/承認0、未解決conversation必須、force push/削除不可をGETで照合した。PRの実行状態は[GitHub Checks](https://github.com/ayutaz/scratch-arcade-os/pull/2/checks)で確認する。

## 根拠

[GitHubのbranch保護](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)、[workflow権限](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)、[uvのDependabot対応](https://docs.astral.sh/uv/guides/integration/dependabot/)、[pip-audit](https://github.com/pypa/pip-audit)。


実sourceの別cloneにもローカル限定のv0.1.0タグを作り、配布CLIで361ファイルのsource archiveを生成した。README.ja.mdの収録、firmware/録音の不在、SHA-256一致を確認。fixtureのタグはpushせず、GitHub Releaseを作成していない。

## 2026-11-20のMac runner指定

PR16のrun44564695682では`macos-15`のhost/target両jobがrunner未割当・step未開始で待機した。`macos-15-intel`を明示し、別の公開Pet CIで成功したIntel環境へ合わせる。`macos-15`が廃止されたという判断ではなく、開始時刻の保証でもない。[GitHub公式仕様](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)で標準公開repo向けIntel labelを確認した。

必須4job名/保護条件、全host試験、固定ESP-IDF build、read-only権限とreport境界は維持する。有料large/self-hostedへの変更や検査の省略は行わない。先行2契約で旧labelのRed→変更後Green。既存CI契約も回帰検査する。

Intel指定のrun44566391991は準備段階で失敗した。固定Zig/host bootstrapがDarwin arm64専用である点を見落としていたため、`macos-26`（標準ARM64）へ修正した。旧失敗を成功に数えず、先行のarchitecture契約でIntel拒否のRedを再現し、同じ3契約と既存CI検査をGreen確認する。最新headの必須4CIを別に待つ。
