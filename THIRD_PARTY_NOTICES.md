# 第三者の権利表示

自作コードはApache-2.0。同梱licenseテキストは条文を保持し、行末空白/末尾空行だけを正規化した。以下の第三者素材へ、その許諾を上書きしない。upstreamのsourceは固定commitから取得し、cacheやビルド済みbinaryをこのsource releaseへ含めない。

| 対象 | 使用範囲 | ライセンス/表示 |
|---|---|---|
| ESP-IDF v6.1 / FreeRTOS / driver | カーネル・周辺/無線・暗号等の基盤 | [IDF root Apache-2.0](licenses/third-party/esp-idf-Apache-2.0.txt)。component個別条件は[一覧](docs/linked-license-inventory.json) |
| ESP Wi-Fi library | target Wi-Fi | [Apache-2.0](licenses/third-party/esp-wifi-Apache-2.0.txt) |
| WAMR2.4.5 | WASM interpreter | [root Apache-2.0](licenses/third-party/wamr-Apache-2.0.txt)、一部SPDXは[LLVM exception](licenses/third-party/LLVM-exception.txt)付き。EMS統計の局所patchは元の表示を生成コピーへ保持 |
| littlefs2.11.3 | raw filesystem | [BSD-3-Clause](licenses/third-party/littlefs-BSD-3-Clause.txt)、componentにも表示を同梱 |
| MicroPython v1.25.0 ASCII font | C HomeのASCII字形 | [元header](assets/fonts/micropython-1.25.0-font_petme128_8x8.h)のMIT/著作権表示を維持。Copyright 2013, 2014 Damien P. George |
| Noto Sans JP派生字形 | 固定日本語Home/app/画像 | [SIL OFL1.1](licenses/third-party/NotoSansJP-OFL.txt)、Copyright 2014-2021 Adobe。派生名Lab OS UI Bitmap等。元TTFは配布しない |

ホストPython依存とtoolchainはuv.lock/固定取得元に従い、依存自体の権利表示も維持する。IDFのcomponent別licenseは元開発のtarget buildからesp-idf-sbomで棚卸しし、公開情報であるname/license/copyrightだけを一覧化した。機器情報やローカルpathはない。この一覧は自作コードへの一括再ライセンスではなく、今後binaryを再配布する場合は、その成果物の依存/表示を改めて照合する。

Apacheの適用/NOTICEについては[ASF公式](https://www.apache.org/legal/apply-license.html)、条文は[Apache License2.0](https://www.apache.org/licenses/LICENSE-2.0.html)を参照する。
