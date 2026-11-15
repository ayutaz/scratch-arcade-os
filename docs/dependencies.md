# 固定依存とライセンス

| 対象 | 固定版/commit | 取得元 |
|---|---|---|
| WAMR | 2.4.5 / 25bd7eb63e828e4bd242cc9b38d260b4b31c6605 | https://github.com/bytecodealliance/wasm-micro-runtime |
| littlefs | 2.11.3 / 6cb4e86540eca0d9ba62500a298385c9d863c8be | https://github.com/littlefs-project/littlefs |
| ESP-IDF | v6.1 / fff9895c82d744c7237be8847347bdd1b07c6643 | https://github.com/espressif/esp-idf |
| Zig | 0.15.2、macOS arm64 | https://ziglang.org/download/0.15.2/ |
| Noto Sans JP | source SHA-256 c2f3b4d463500a2ddcd3849cded1fceeb9fd6d1c32e6cbecd568453ba50fc68f | google/fontsの固定29b4ec6df2522a8aee279414b78a07910b065874 |

取得URL/checksumは[bootstrap.py](../tools/bootstrap.py)、Python依存は[uv.lock](../uv.lock)、IDFのPythonは[分離lock](../firmware/esp-idf/host-tools/uv.lock)。フォント原本は字形再生成テスト用で、生成済み字形はsource releaseに含める。

[第三者NOTICE](../THIRD_PARTY_NOTICES.md)と[component別のlicense/copyright一覧](linked-license-inventory.json)を参照。source releaseには純正binary、抽出コード、上流依存cache、録音/秘密情報を含めない。CIのmacOS arm64選択は[GitHub公式runner表](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)に基づく。


## IDFのPython依存の保守

CIの既知脆弱性監査でcryptography48.0.1に3種類の既知問題（照合結果は重複を含み6件）が見つかり、50.0.2へ固定更新した。root側には既知の検出はなかった。

固定IDF v6.1の取得済みconstraintsはcryptography<49を要求するため、公式のself-managed mode（IDF_PYTHON_CHECK_CONSTRAINTS=0）を使い、IDF用uv.lockで全依存を管理する。constraints原本のchecksum検査は維持し、内容を改変しない。これは上流の版上限を外す指定であり、idf_toolsの必要パッケージ/推移依存チェックを止める指定ではない。新しい版の互換性は依存検査とS3ビルドで確認し、脆弱性をignoreして通さない。

根拠: [公式idf_tools.pyのself-managed設定](https://github.com/espressif/esp-idf/blob/fff9895c82d744c7237be8847347bdd1b07c6643/tools/idf_tools.py)、[cryptography修正履歴](https://cryptography.io/en/latest/changelog/)。監査は既知のPython問題が対象で、IDF/C依存全体の安全性を保証しない。
