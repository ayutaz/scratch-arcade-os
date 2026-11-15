# 開発規則

- 作業開始時にgit statusと本ファイルを確認し、既存変更を保護する。
- Python3.12.13、環境/依存/実行はuvのみ。pip/manual venvを使わない。
- 実装は先行テストで意図したRed→最小実装Green→回帰。試験不備の失敗を機能のRedと数えない。
- `uv run --locked python tools/test.py`でホスト試験を実行する。skipは成功に数えない。
- host/ターゲットbuild/実機/ユーザー確認を区別し、詳細な開発記録は日本語。README.mdは英語を標準とし、README.ja.mdと内容を同期する。
- Flash/実機更新はimage/hash/領域/影響/保全/復旧を提示して個別許可を得る。このOSSリポジトリへの貢献を実機操作の許可と扱わない。
- scripts/flash.shの拒否を解除しない。未知GPIO、eFuse/security、PSRAM有効化を推測で実行しない。
- 純正binary/抽出コード/Flash原本/録音/資格情報/実機ID/生ログ/依存cacheをGitへ入れない。
- Apache-2.0と第三者license/著作権表示を維持する。フォント派生データはOFLの境界を保つ。
- 機能単位で検証/差分確認/commit/push。mainへ直接pushせず、作業branchとPRを使い、必須CI成功後に通常mergeする。管理者の迂回merge・履歴改変・force pushは行わない。
- CI/CDとmain保護の正本はdocs/ci-cd.mdと.github/main-protection.json。検査失敗をcontinue-on-errorやskipで成功扱いにしない。新Releaseは版と対象を確認し、source-onlyの境界を維持する。

- READMEは初めて読む人向けに、できること・Macでの試し方・実機との違いを先に示す。内部API上限、ディレクトリ一覧、詳細な検証履歴はdocsへ置き、英語版と日本語版を同期する。
