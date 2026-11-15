# 開発規則

- 作業開始時にgit statusと本ファイルを確認し、既存変更を保護する。
- Python3.12.13、環境/依存/実行はuvのみ。pip/manual venvを使わない。
- 実装は先行テストで意図したRed→最小実装Green→回帰。試験不備の失敗を機能のRedと数えない。
- `uv run --locked python tools/test.py`でホスト試験を実行する。skipは成功に数えない。
- host/ターゲットbuild/実機/ユーザー確認を区別し、ドキュメントは日本語で記録する。
- Flash/実機更新はimage/hash/領域/影響/保全/復旧を提示して個別許可を得る。このOSSリポジトリへの貢献を実機操作の許可と扱わない。
- scripts/flash.shの拒否を解除しない。未知GPIO、eFuse/security、PSRAM有効化を推測で実行しない。
- 純正binary/抽出コード/Flash原本/録音/資格情報/実機ID/生ログ/依存cacheをGitへ入れない。
- Apache-2.0と第三者license/著作権表示を維持する。フォント派生データはOFLの境界を保つ。
- 機能単位で検証/差分確認/commit/push。履歴改変やforce pushは行わない。
