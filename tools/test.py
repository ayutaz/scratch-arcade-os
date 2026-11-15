"""ホスト試験を実行し、skipを成功として扱わない。"""
import argparse
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
def main(argv=None):
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--start-directory',default=str(ROOT/'tests'));args=p.parse_args(argv)
 sys.path.insert(0,str(ROOT/'prototypes/lab-os'))
 suite=unittest.defaultTestLoader.discover(args.start_directory)
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 if result.skipped:
  print('Skipped tests are not accepted; prepare the pinned prerequisites.',file=sys.stderr);return 1
 return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
