"""Include the real ES-module handler contract in the normal ingestion suite."""
from pathlib import Path
import subprocess
import unittest


class ManagedRelayEdgeTests(unittest.TestCase):
    def test_existing_edge_handler_relay_contract(self):
        script=Path(__file__).with_name('managed_massive_relay_v2.test.mjs')
        result=subprocess.run(['node',str(script)],capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__': unittest.main()
