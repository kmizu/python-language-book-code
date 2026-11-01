import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CODE = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def execute(self, source, engine='vm'):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '買い物.mame'
            path.write_text(source, encoding='utf-8')
            return subprocess.run([sys.executable, '-X', 'utf8', str(CODE / 'mame.py'),
                                   str(path), '--engine', engine], capture_output=True,
                                  text=True, encoding='utf-8')

    def test_tree_and_vm_output(self):
        for engine in ('tree', 'vm'):
            result = self.execute('let price = 80; print 100 + price * 3;', engine)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '340\n')

    def test_error_has_nonzero_exit(self):
        result = self.execute('print missing;')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')
        self.assertIn('UndefinedNameError', result.stderr)


if __name__ == '__main__':
    unittest.main()
