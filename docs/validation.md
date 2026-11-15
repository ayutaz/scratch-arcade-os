# 検証記録

2026-11-16 JST。公開するsource treeと、元の実機開発の結果を分ける。この切り出しでは実機接続/転送/Flash書込み/録音を行っていない。

## 今回のホスト・build

| 検査 | 結果 |
|---|---|
| 公開境界/取得ツール | 未実装Red→9件Green、Flash拒否追加Red→10件、IDF constraints取得追加Red→11件Green |
| 全体ホスト回帰 | 675件/skipなし成功（87.031秒）。後続constraintsの追加契約を含む対象11件も成功 |
| 固定依存取得 | Zig checksum、WAMR/littlefs commit、フォントhashを実際に取得・照合。既存改変/alias/traversal/危険tarを拒否 |
| ESP32-S3 build | 新しいsource treeからcandidateリンク成功、app910,368B。Flash書込みなし |
| 旧Privateとの分離 | OS/SDK/6appとホストfixtureを選択してコピー。純正抽出parserと実機固有の配備/復元ツールは含めない |
| 依存/権利 | ESP-IDF component別license/copyrightを棚卸しし、NOTICE/OFL/MIT/LLVM例外等を維持 |

初回のホスト試験は674件中1件でPrivateのremote_timer_trialを参照して失敗。公開する基本5本＋追加6本を直接buildするfixtureへ変更し、同じ33起動/終了・160KiB・解放の契約を維持して13件Green→全体675件Greenにした。試験を削除/skipして通していない。

初回target buildはIDF constraintsファイル不足で停止。取得/再利用/改変拒否を先行テストで追加し、公式URL/checksumで補完後にbuild成功。試験中のmacOS一時pathの/varと/private/varの差はfixtureを正規化し、機能のRedと数えない。

## 元の実機開発で確認した範囲

| 対象 | 結果 |
|---|---|
| OS | 729f/8MiB/S3、内部160KiB VM pool、PSRAM無効 |
| 11app | 保存版2appだけ更新、他9本hash不変、全11本起動/終了 |
| 保存 | Lane Catcherの最高得点2、Focus Timer設定70秒を通常再起動後にCRC照合 |
| 通信/音声 | Macから開始/重複再送/停止/照会/リセット/10秒完了、Wi-Fi停止後の同session32,000frames録再/消去/解放 |
| 人の確認 | 前版778eで4app表示/移動/X/B/FN+B、8379で声の再生/雑音改善・日本語/2秒の声 |

今回再buildした公開source版を実機へ再書込みした結果ではない。最新729fの聴取品質/実LCD/実キーを再確認したとは記載しない。フレーム数とCRCは音質/物理発色/入力の保証ではない。

PSRAM全容量、実電断、無期限稼働、任意native fault、未知appの互換性、BLE/音声AIは未確認/未実装。新cloneの再現と公開対象/履歴の最終検査は、次節へ記録する。


## 新しいGit cloneでの再現

初期source commit53a34ffをcacheなしの別ディレクトリへcloneし、READMEと同じuv sync→bootstrap --font→公開境界検査→tools/test.pyを実行した。公開upstreamから依存を取得し、元のPrivateプロジェクトのソース/依存cacheをコピーせずに**676件/skipなし成功（99.314秒）**を確認した。rootとIDFのPythonは分離uvで管理する。

S3 buildは公開source treeで固定公開依存の既存cacheを複製して実施したもので、target toolchainをすべてネットから再取得した試験ではない。生成物のbyte完全一致も未検証。

公開するGit indexだけを別領域へ書き出し、Gitleaks8.30.1で検査して検出0。新しいGit履歴も検出0。最初のcache込み走査が上流の試験データ等へ反応した結果は、公開sourceの漏洩と区別した。全追跡ファイルの境界検査・README等のローカル参照・diff検査も成功した。

秘密情報検査は検出器が見つけられる形式に限られ、未知の秘密が絶対にないという保証ではない。source-onlyの公開で、firmware binary・実機の原本/録音/資格情報を含めない。[機械可読の結果](validation.json)。
