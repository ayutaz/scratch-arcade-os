# 日本語音声サービスの候補

2026-11-17 JST。初版の固定image1affは個別許可後に1台へ適用し、Petの操作/返答/資源解放を自動確認。合成5語の音響試験は操作0/5。入力DC補正版c032は追加の固定レビュー/個別許可後に1台へ適用し、起動前全量一致と16app保持を確認した。認識品質の判定は[Petの実機記録](https://github.com/ayutaz/arcade-ai-pet/blob/main/docs/device-validation.md)へ分離する。
5操作の固定KWSと5つの返答を、既存の音声leaseへ接続した。
自由文ASR、自由会話、本体内TTS、常時待受ではない。

## アプリAPI

| API | 権限 | 動作 |
|---|---|---|
| audio_record(2000) | microphone | 既存の2秒録音を開始 |
| audio_classify() | microphone | 完了済み録音を1回だけ消費し、分類後にPCM/推論scratchを消去 |
| audio_reply(id) | speaker | 事前合成した短い返答を再生。IDは0〜4 |
| audio_stop() | 音声lease | 中止/消去。終了時も既存の所有/cleanup規則を適用 |

classifyの戻り値は-1未準備/失敗、0あそぼ、1おいで、2まって、3おやすみ、
4ありがとう、5対象外、6無音。5/6ではペットの状態を変更しない。
replyは-1不正/未対応、0busy/開始失敗、1受付。各APIは既存の2mutation/frameを共有する。
不正なspeaker/microphone権限、返答ID、backend戻り値を両VMで検査する。
旧ABI2 FWは新importを解決できないため、ABI番号だけで互換と判断しない。

## 実行と保護

録音は本体RAM内の8bankだけに保持する。KWSは同じbankを直接読み、別の64KBを確保しない。
認識済みPCMは再認識/録音再生できず、新しい録音が必要。raw PCMをguest/USB/networkへ返すAPIはない。
返答も同じ音声bufferを消去してから使い、最大±3277、5ms fade、分割I/Oを維持する。
全5素材は1秒以内なので、既存のspeaker専用32KBでも収まる。

推論は1回のnative呼出しで固定32000samplesを処理する。guest fuelだけではnativeを中断できず、
実S3の遅延/GUI停止時間/WDT余裕は未測定。録音を消費するため同じPCMで連続推論できない。
アプリの異常終了/中止は既存cleanupへ渡し、driver close失敗時は所有を保持して次のappを止める。
native faultをMMUで隔離する仕組みではない。

## 資源と評価範囲

| 対象 | 値 |
|---|---:|
| KWS重み | 17,380B、Flashのconst |
| 返答PCM8 | 25,418B、Flashのconst |
| Cの特徴scratch | 5,680B |
| OSのLabVoice全体 | 6,752B（特徴出力/logitを含むstatic領域） |
| 既存録音PCM | 64,000B、内部RAMの遅延確保 |
| 候補app.bin | 966,016B / slot1,048,576B、空き82,560B |
| リンク時DIRAM | 使用292,815B / 残48,945B。実heapとは別 |

PSRAM、GPIO、Flash配置、eFuse/securityは変更していない。
build値はこの候補sourceの値で、将来の固定適用レビューとは別。実heap/stack/処理時間は実機検証が必要。
元のモデルは新規合成956例でF1=0.978908、C/Python判定一致。人の声の精度ではない。
素材・条件は[音声component](../components/voice/NOTICE.md)。

## TDDと追加検証

| 対象 | 意図したRed | Green |
|---|---|---|
| 音声service | C実装/固定モデル欠落でcompile失敗 | 3件、0.934秒。完了録音のみ/消費と消去/5返答/権限/cleanup失敗 |
| SDK/両VM | 新import未登録で2件失敗 | audio SDK27件、1.189秒。戻り値範囲/権限/ID/共有quota |
| targetのcallback設定 | set_voice未宣言でcompile失敗 | board sound9件、0.351秒。閉じている時だけ設定/次leaseへ保持 |
| 音声回帰 | 追加検証 | 既存音声80件、6.646秒 |

```sh
uv run --locked python -m unittest discover -s tests -p test_labos_voice_service.py -v
uv run --locked python -m unittest discover -s tests -p test_labos_audio_sdk.py -q
uv run --locked python -m unittest discover -s tests -p test_labos_board_sound.py -v
uv run --locked python tools/test.py
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.target build-candidate
PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.target size-candidate
```

最初のtarget buildは上流Cの連続ifがGCCのmisleading-indentationで拒否された。
警告を無効にせず上流の改行を直し、956例の再監査後に再取得してbuild成功。
Red/Greenは動作追加の先行契約に限り、この書式修正やbuildを後付けTDDと呼ばない。

上の初版build/試験は当時の記録。現在は1aff/Petを含む16appで、次の補正を含む新imageは別の固定レビュー/個別許可が必要。

全体回帰は最初697件中1件失敗。candidate entryの模擬リンクに新callbackのstubが
不足していたため、呼出し順/失敗時にbootを続けないケースも含めてfixtureを更新した。
既存のboot/FS/telemetry/cleanupの検査を残し、target契約5件Green（1.544秒）。
全体697件/skipなしGreen（82.772秒）。これは実機確認ではない。

## 2026-11-17: 認識前の入力DC補正

実機の環境音2秒の集計は平均1,721、RMS1,724、AC RMS112。PCMは取得していない。
初版の分類はPDM入力の平均を除去せず、固定frontendへそのまま渡していた。
合成5語へ一定値1,600を加える別のホスト探索でも認識が崩れ、平均除去後は元の操作へ戻った。
これらはDCが原因の候補である証拠で、音響試験の不反応が解決した証明ではない。

- 既存の完了録音/権限/driver解放を検査した後、消費する専用PCM内だけで平均を除去する。
- 中間値はint32/int64。16bit範囲外は飽和させる。連続/bankedの両方を扱い、追加PCM buffer/確保を使わない。
- 固定の特徴抽出・重み・返答は変更せず、元の録音と推論scratchは従来通り消去する。
- 返答/汎用録音再生/原本の保存方法は変更しない。

先行テストは「一定値だけの録音は無音」。banked/連続の各±1,600とint16の両端を検査し、8条件全てが対象外5となる意図したRedを確認。
最小実装後は音声service全4件Green（0.551秒）、各8条件が無音6で、PCM/scratch消去も成功。

```sh
uv run --locked python -m unittest discover -s tests -p test_labos_voice_service.py -v
```

全回帰/対象build/CIと実機は分けて記録する。修正実装時点では実声・音響経路は未検証。後続の適用結果は次節へ記録する。

全回帰の初回は701件中、公開候補一覧のfixtureがworktreeの`.git`ポインタfileを含めたため1エラー。
Git metadataの除外をdirectoryだけでなく、このfileにも適用した。実際の公開境界checkerは`.git`を拒否するまま。
この環境/試験fixtureの修正は、音声機能の先行Redには数えない。

補正後の全回帰701件/skipなしGreen（82.267秒）。Markdown参照74件と公開境界378ファイルも成功。対象build/必須CIと実機は別工程。

## 入力補正版の固定適用

2026-11-17 JST。source56ff39e、PROJECT_VER=56ff39e、966,176B、SHA-256 `c0327a6929df379e05b1e5538bcc2bf74419959ee9c8780f69a06f1da841c143`。
固定レビューへの個別許可後、app offset0x10000だけを1回更新した。
直前Flash8MiBを2回取得してbyte/容量/SHAを照合し、reset前の8MiB読戻しが期待値と一致。
対象外sector・bootloader/partition・NVS/専用FSを保持し、正常boot/READY/全16appの版/hash不変を確認した。
GPIO/PSRAM/eFuse/securityは変更せず、raw PCMを取得していない。原本Flash・機器ID・生ログ・binをこのrepoへ公開しない。

この結果は配備/保全/起動であり、音声認識の改善や人の声による合格とは別。固定1回許可は使用済みで、再試行・自動復元・別imageは含まない。

最新の操作/音響結果は[Petの実機記録](https://github.com/ayutaz/arcade-ai-pet/blob/main/docs/device-validation.md)を参照。ここへ記載した配備結果だけを認識品質の証拠としない。

## 2026-11-18: v3候補と分類診断

実機c032はKWS v2のまま。以下は新しいsource/ホスト試験の結果で、実機へ適用していない。

- [Pet source595f5d7](https://github.com/ayutaz/arcade-ai-pet/tree/595f5d7d9cf06c08165e160d9d46040f326ef0ad)のv3を固定して取り込んだ。[来歴/ライセンス](../components/voice/NOTICE.md)。
- 重み23,884B、260→88→7、閾値995。HP160→平均除去→peak4,096→adaptive MFCC。PCMは既存bank/連続buffer内で消費し、scratch5,680Bと出力を消去する。
- 上流の固定合成8条件×956例は全条件合格、Cとの判定/直接integer logit/分割bufferの特徴は7,648件一致。実声やS3の性能ではない。
- 返答素材、guest ABI2、GPIO/PSRAM、Flash配置は変更しない。新しいFWの実機適用は個別レビュー/許可が必要。

### scalar診断の契約

`Client.voice_status()`はUSB管理op15 / control5、payload4Bの読み取り専用要求。
返答は80B、schema1。未分類/HOME/cleanup/mic permissionなしは`available=0`と残りzero。
現在のmic owner/leaseだけが次の値を読める。PCM・MFCC・logit・任意memoryを返さない。

| 値 | 意味 |
|---|---|
| sequence / lease_generation | 現在lease内の分類試行とlease識別子。停止/再取得で前の観測を隠す |
| result | 0〜4操作、5対象外、6無音、-1明示エラー。画面だけの無反応7とは別 |
| errors | このlease内のnative分類エラー累計。過去のerrorを後の成功で0に戻さない |
| frames / minimum / maximum / mean / rms / ac_rms / centered_peak / saturated_frames | 分類直前の全入力集計。完全録音時は32,000frames、未完了等の拒否時は0 |
| first_mean_1024 / last_mean_1024 | 入力の先頭/末尾1,024samplesの平均。声だけのSNRとは呼ばない |
| features_ok / model_revision / observed_at_ms | 特徴生成の成否、model3、分類呼出し時のOS loop時刻。推論終了時刻やPCの時刻ではない |

入力集計は分類前、PCM/scratchは分類後に消去。残るのは最後のscalarだけで、失敗した試行もsequence/result/errorsへ反映する。
このproviderのprivate opcode65,536はguest bindingから拒否する。trusted USBからだけ現在の稼働app/permissionで問い合わせる。
旧FWではcontrol5が未対応のため、固定版を確認してから使う。parserは余分なpadding/不整合/旧model等を拒否して接続を失敗状態にする。

### 先行テスト

- 時間変動するDCの生成入力: 連続/分割で旧5→期待6の2失敗Red、v3移植後Green。実機の原因証明ではない。
- scalar診断: unsupported native queryの-1→期待0のRed後に実装。結果/集計、guest拒否、owner/lease分離、明示error、buffer消去を確認。
- wire: upload中のop5拒否Red→読み取り成功、upload/app数維持。BSPのHOME/稼働appのpacketも先行Redから確認。
- client: 新method欠落Red→分類/未取得/明示errorと不正packetの拒否を確認。
- 補助のPCM注入/診断passthroughは最初にhook欠落を確認して作成。mockの初期参照不足や、2回目の録音で試験時計を巻き戻した失敗は製品Redへ数えない。

```sh
uv run --locked python -m unittest discover -s tests -p test_labos_voice_service.py -v
uv run --locked python -m unittest discover -s tests -p test_voice_snapshot_client.py -v
uv run --locked python -m unittest discover -s tests -p test_voice_component_v3.py -v
uv run --locked python -m unittest discover -s tests -p test_labos_transfer.py -v
uv run --locked python -m unittest discover -s tests -p test_labos_board_session.py -v
```

BSP packet試験のproviderは決定的scalarのprotocol fixtureで、実際の録音証拠ではない。
別の音声service試験は生成PCMと実Cモデルを使う。どちらも実LCD/聴取/物理入力の保証へ広げない。
生PCMや実機IDはGitへ保存しない。

### 全回帰とターゲットビルド

2026-11-18、`uv run --locked python tools/test.py`は715件/86.339秒、skipなしで成功。
`PYTHONPATH=prototypes/lab-os uv run --locked python -m labos.target build-candidate`も成功した。
ESP-IDF v6.1の固定sourceと固定Xtensa toolchainを使用し、書き込みは実行していない。

候補binは974,080B（0xEDD00）、1MiB app slotの残り74,496B。これは未コミットsourceでの予備ビルドで、適用対象の固定imageではない。
source確定後の再ビルドで版・SHA・サイズ・対象sectorを改めて固定する。
`LabVoice`は8,192B以下のcompile-time制約を通過。実heap/stack、推論遅延、実声の品質は未測定。
GPIO・PSRAM・partitionを変更しておらず、実機c032の1回許可を新candidateへ流用しない。

`size-candidate`の静的DIRAMは292,895B（.bss 200,968B、.data 21,892B、.text 70,035B）、当該表示領域の残り48,865B。
sizeの総image報告973,971Bとpaddingを含むbinの974,080Bを区別する。
この静的残量を、起動後のheapや音声録音中に使える連続RAMの値とは扱わない。
