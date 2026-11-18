from pathlib import Path
import struct,sys,unittest
from unittest.mock import Mock
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.transfer import Client,TransferError

FORMAT='<3Ii2I3i4I2i4I'


def packet(values):return struct.pack(FORMAT,*values)+bytes(4)


class VoiceSnapshotClientTests(unittest.TestCase):
    def client(self,reply):
        client=Client.__new__(Client);client.failed=False;client._request=Mock(return_value=reply)
        return client
    def good(self):return [1,1,7,6,0,32000,1600,1600,1600,1600,0,0,0,1600,1600,1,3,2000,1]

    def test_classification_and_input_metrics_are_read_only_scalars(self):
        client=self.client(packet(self.good()));result=client.voice_status()
        client._request.assert_called_once_with(15,struct.pack('<I',5))
        self.assertEqual(result['result'],6);self.assertEqual(result['sequence'],7)
        self.assertEqual(result['frames'],32000);self.assertEqual(result['mean'],1600)
        self.assertEqual(result['first_mean_1024'],1600);self.assertEqual(result['last_mean_1024'],1600)
        self.assertEqual(result['lease_generation'],1);self.assertFalse(client.failed)

    def test_unavailable_and_explicit_native_error_remain_distinct(self):
        result=self.client(packet([1]+[0]*18)).voice_status()
        self.assertEqual(result['available'],0)
        values=self.good();values[2]=8;values[3]=-1;values[4]=1;values[5:16]=[0]*11
        result=self.client(packet(values)).voice_status()
        self.assertEqual(result['available'],1);self.assertEqual(result['result'],-1)
        self.assertEqual(result['errors'],1);self.assertEqual(result['frames'],0)

    def test_noncanonical_or_inconsistent_snapshot_poison_the_connection(self):
        cases=[]
        for index,value in [(0,2),(1,2),(2,0),(3,7),(5,31999),(11,1),(12,32001),(13,3000),(15,0),(16,2),(18,0)]:
            values=self.good();values[index]=value;cases.append(packet(values))
        values=self.good();values[1]=0;cases.append(packet(values))
        cases.extend([packet(self.good())[:-1],packet(self.good())[:-1]+b'\x01'])
        for data in cases:
            with self.subTest(data=data[:24]):
                client=self.client(data)
                with self.assertRaises(TransferError):client.voice_status()
                self.assertTrue(client.failed)


class VoiceScoresClientTests(unittest.TestCase):
    client=VoiceSnapshotClientTests.client
    def good(self):return [1,1,9,5,1,2,100,99,1,995,3,5000,1]
    def packet(self,values):return struct.pack('<3Ii2I2i5I',*values)+bytes(28)
    def test_rejected_command_is_distinct_from_an_unknown_top_class(self):
        c=self.client(self.packet(self.good()));r=c.voice_scores()
        c._request.assert_called_once_with(15,struct.pack('<I',6))
        self.assertEqual((r['result'],r['top1'],r['margin_q10'],r['threshold_q10']),(5,1,1,995))
        v=self.good();v[4:6]=[5,2];v[6:8]=[2000,0];v[8]=2000
        self.assertEqual(self.client(self.packet(v)).voice_scores()['top1'],5)
    def test_unavailable_has_no_stale_scores_and_signed_extremes_are_valid(self):
        self.assertEqual(self.client(self.packet([1]+[0]*12)).voice_scores()['available'],0)
        v=self.good();v[3]=1;v[6:9]=[2147483647,-2147483648,4294967295]
        self.assertEqual(self.client(self.packet(v)).voice_scores()['margin_q10'],4294967295)
    def test_inconsistent_padding_ranking_margin_or_decision_poison_connection(self):
        cases=[]
        for index,value in [(0,2),(1,2),(2,0),(3,-1),(4,7),(5,1),(6,98),(8,2),(9,0),(10,2),(12,0)]:
            v=self.good();v[index]=value;cases.append(self.packet(v))
        v=self.good();v[3]=1;cases.append(self.packet(v))
        v=self.good();v[1]=0;cases.append(self.packet(v))
        cases += [self.packet(self.good())[:-1],self.packet(self.good())[:-1]+b'\1']
        for raw in cases:
            c=self.client(raw)
            with self.subTest(raw=raw[:20]),self.assertRaises(TransferError):c.voice_scores()
            self.assertTrue(c.failed)
