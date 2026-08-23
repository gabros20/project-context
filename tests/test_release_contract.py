import pathlib
import subprocess
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts" / "check_release.py"


class ReleaseContractTests(unittest.TestCase):
    def run_check(self, tag: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECK), tag],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def test_current_release_contract(self):
        proc = self.run_check("v0.4.0")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("release contract valid: v0.4.0", proc.stdout)

    def test_mismatched_tag_is_rejected(self):
        proc = self.run_check("v0.4.1")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("does not match package version", proc.stderr)


if __name__ == "__main__":
    unittest.main()
