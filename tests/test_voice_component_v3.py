import hashlib,json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


class VoiceComponentV3Tests(unittest.TestCase):
    def test_component_uses_fixed_licensed_channel_model_and_source_hashes(self):
        base=ROOT/'components/voice';meta=json.loads((base/'provenance.json').read_text())
        self.assertEqual(meta['weights_bytes'],23884)
        self.assertEqual(meta['commit'],'595f5d7d9cf06c08165e160d9d46040f326ef0ad')
        self.assertEqual(meta['runtime'],'channel-adaptive-v1')
        self.assertEqual(meta['reply_bytes'],25418)
        for name,row in meta['files'].items():
            self.assertEqual(Path(name).name,name)
            self.assertEqual(hashlib.sha256((base/name).read_bytes()).hexdigest(),row['sha256'],name)
        channel=json.loads((base/'channel-metadata.json').read_text())
        self.assertEqual(channel['weights_sha256'],'374987a02446e805f18427d7de8de3cd955c4833efc6e0a9dbd9fa655c3c59f2')
        self.assertEqual(channel['threshold_q10'],995)
        self.assertEqual(channel['input_contract'],dict(conditioning='hp160',frontend='adaptive',peak=4096,samples=32000,rate=16000))
