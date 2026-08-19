import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CTX = ROOT / "scripts" / "ctx.py"
INSTALL = ROOT / "scripts" / "install.py"


def run_ctx(args, cwd=None, check=True):
    proc = subprocess.run([sys.executable, str(CTX), *args], cwd=cwd, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and proc.returncode != 0:
        raise AssertionError(f"ctx failed: {proc.stdout}\n{proc.stderr}")
    return proc


def git(repo, *args):
    proc = subprocess.run(["git", "-C", str(repo), *args], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return proc.stdout.strip()


class InstallSafetyTests(unittest.TestCase):
    def test_existing_repo_instructions_are_appended_and_backed_up(self):
        with tempfile.TemporaryDirectory() as td:
            repo = pathlib.Path(td)
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "test@example.com")
            git(repo, "config", "user.name", "Test")
            (repo / "README.md").write_text("hello\n", encoding="utf-8")
            git(repo, "add", "README.md")
            git(repo, "commit", "-q", "-m", "init")

            agents_original = "# Existing Agents\n\nKeep this exact content.\n"
            claude_original = "# Existing Claude\n\nDo not replace these instructions.\n"
            (repo / "AGENTS.md").write_text(agents_original, encoding="utf-8")
            (repo / "CLAUDE.md").write_text(claude_original, encoding="utf-8")

            run_ctx(["--cwd", str(repo), "init", "--instructions"])

            agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
            claude = (repo / "CLAUDE.md").read_text(encoding="utf-8")
            self.assertTrue(agents.startswith(agents_original))
            self.assertTrue(claude.startswith(claude_original))
            self.assertIn("<!-- project-context:begin -->", agents)
            self.assertIn("<!-- project-context-import:begin -->", claude)
            self.assertIn("@AGENTS.md", claude)
            self.assertEqual((repo / "AGENTS.md.project-context.bak").read_text(encoding="utf-8"), agents_original)
            self.assertEqual((repo / "CLAUDE.md.project-context.bak").read_text(encoding="utf-8"), claude_original)

    def test_existing_claude_settings_are_merged_and_backed_up(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            settings = home / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True)
            original = {
                "permissions": {"allow": ["Bash(git status)"]},
                "env": {"EXISTING": "yes"},
                "hooks": {
                    "Stop": [{
                        "matcher": "existing",
                        "hooks": [{"type": "command", "command": "echo existing"}]
                    }]
                }
            }
            original_text = json.dumps(original, indent=4) + "\n"
            settings.write_text(original_text, encoding="utf-8")
            (home / ".agent-skills" / "project-context").mkdir(parents=True)

            env = os.environ.copy()
            env["HOME"] = str(home)
            proc = subprocess.run([sys.executable, str(INSTALL), "hooks", "--hosts", "claude", "--scope", "user"],
                                  env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode != 0:
                raise AssertionError(f"install failed: {proc.stdout}\n{proc.stderr}")

            merged = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(merged["permissions"], original["permissions"])
            self.assertEqual(merged["env"], original["env"])
            existing_commands = [
                h.get("command")
                for group in merged["hooks"]["Stop"]
                for h in group.get("hooks", [])
            ]
            self.assertIn("echo existing", existing_commands)
            self.assertTrue(any("project-context" in (cmd or "") for cmd in existing_commands))
            self.assertNotIn("$schema", merged, "existing settings should not gain unrelated top-level fields")
            backup = settings.with_name("settings.json.project-context.bak")
            self.assertEqual(backup.read_text(encoding="utf-8"), original_text)

            first = settings.read_bytes()
            proc2 = subprocess.run([sys.executable, str(INSTALL), "hooks", "--hosts", "claude", "--scope", "user"],
                                   env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertEqual(proc2.returncode, 0)
            self.assertEqual(settings.read_bytes(), first, "second install should be idempotent and not rewrite settings")

    def test_invalid_existing_claude_settings_are_refused(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            settings = home / ".claude" / "settings.json"
            settings.parent.mkdir(parents=True)
            original = "{ invalid json\n"
            settings.write_text(original, encoding="utf-8")
            (home / ".agent-skills" / "project-context").mkdir(parents=True)
            env = os.environ.copy()
            env["HOME"] = str(home)
            proc = subprocess.run([sys.executable, str(INSTALL), "hooks", "--hosts", "claude", "--scope", "user"],
                                  env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(proc.returncode, 0)
            self.assertEqual(settings.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
