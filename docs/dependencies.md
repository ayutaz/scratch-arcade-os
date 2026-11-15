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
