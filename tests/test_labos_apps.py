import json,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
from labos.build import build,COMPILER
from labos.sdk import Session

@unittest.skipUnless(COMPILER.exists(),'local C compiler unavailable')
class AppTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.apps={n:build(n,Path(cls.tmp.name)) for n in ('game','counter')}
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def session(self,name,**kwargs):
  m,b=self.apps[name];s=Session(b,m,**kwargs);self.addCleanup(s.close);return s
 def test_counter_counts_edges_and_releases(self):
  s=self.session('counter',initial_held=1)
  s.frame(1,10);self.assertEqual(s.debug('debug_value'),0)
  s.frame(0,20);s.frame(1,30);s.frame(1,40)
  self.assertEqual(s.debug('debug_value'),1)
  s.frame(0,50);s.frame(2,60);self.assertEqual(s.debug('debug_value'),0)
  self.assertTrue(s.frame(64,70));self.assertTrue(s.closed)
 def test_game_time_partition_independent(self):
  a=self.session('game');b=self.session('game')
  a.frame(16,0);b.frame(16,0)
  a.frame(1,300)
  for t in (17,83,135,300):b.frame(1,t)
  self.assertEqual(a.debug('debug_x'),24);self.assertEqual(b.debug('debug_x'),24)
  self.assertEqual(a.debug('debug_value'),1)
  self.assertEqual(b.debug('debug_elapsed'),300)
 def test_game_bounds_reset_and_exit(self):
  s=self.session('game');s.frame(16,0);s.frame(1|4,10000)
  self.assertEqual(s.debug('debug_x'),72);self.assertEqual(s.debug('debug_y'),232)
  s.frame(32,10001);self.assertEqual(s.debug('debug_x'),0)
  self.assertTrue(s.frame(64,10002))
 def test_hash_and_abi(self):
  for m,b in self.apps.values():
   self.assertEqual(m['abi'],2)
   import hashlib
   self.assertEqual(m['sha256'],hashlib.sha256(b).hexdigest())
 def pixel(self,session,x,y):
  color=0
  for left,top,w,h,c in session.commands:
   if left<=x<left+w and top<=y<top+h:color=c
  return color
 def test_counter_shows_zero_one_and_reset_as_visible_digits(self):
  s=self.session('counter');s.frame(0,0)
  self.assertEqual(self.pixel(s,30,80),65535)
  self.assertEqual(self.pixel(s,50,90),65535)
  s.frame(1,10)
  self.assertEqual(self.pixel(s,30,80),0)
  self.assertEqual(self.pixel(s,50,90),65535)
  self.assertGreater(sum(w*h for x,y,w,h,c in s.commands if c==65535),200)
  s.frame(32,20);self.assertEqual(self.pixel(s,30,80),65535)
 def test_game_shows_score_change_in_its_own_canvas(self):
  s=self.session('game');s.frame(16,0)
  self.assertEqual(self.pixel(s,120,20),65535)
  s.frame(1,300)
  self.assertEqual(s.debug('debug_value'),1)
  self.assertEqual(self.pixel(s,120,20),0)
  self.assertEqual(self.pixel(s,140,30),65535)
