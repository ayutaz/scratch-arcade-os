# 固定音声モデルと返答素材

[Arcade AI Pet](https://github.com/ayutaz/arcade-ai-pet)の固定sourceを選択して取り込んだ。
正確なcommit、元path、各hashは[provenance.json](provenance.json)。上流TTSモデルや本体録音は含まない。

| 対象 | 条件 |
|---|---|
| kws_features.c / kws_inference.c / pet_kws.h / feature_tables.h | Apache-2.0 |
| pet_model.h | 合成音声から学習した17,380B KWS重み、CC BY 3.0、[帰属](LICENSE-KWS.txt) |
| replies.h | M001の事前生成音声25,418B、CC BY 3.0、[帰属](LICENSE-REPLIES.txt) |

KWSはHTS Voice Mei（MMDAgent Project Team）とNIT ATR503 M001（HTS Working Group）由来。
©2009–2018 Nagoya Institute of Technology（Mei）、©2003–2012 Nagoya Institute of Technology /
©2003–2008 Tokyo Institute of Technology（M001）。合成・加工・学習・量子化・C変換を行った。
返答はM001だけを合成し、DC除去・低域通過・8kHz化・PCM8化・fadeを適用した。
機関/著作者の推薦を示すものではない。

[上流モデルカード](https://github.com/ayutaz/arcade-ai-pet/blob/975ef913f91c417cd715c23eae8099c140d965db/models/kws-v2/model-card.md)、
[返答の詳細](https://github.com/ayutaz/arcade-ai-pet/blob/975ef913f91c417cd715c23eae8099c140d965db/assets/replies-v1/model-card.md)。
C表の内部コメントにある相対pathは上流repoでの配置を示す。このOSでの条件は本NOTICEと同梱licenseを参照。

OS実装のApache-2.0で声の素材まで一括再許諾しない。現在のReleaseはsource-onlyで、
firmware binaryの新配布は行っていない。改変buildを配布する場合も本帰属/条件を保持する。
