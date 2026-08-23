import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CTX = ROOT / "scripts" / "ctx.py"
INSTALL = ROOT / "scripts" / "install.py"


def command(args, cwd=None, input_text=None, env=None, check=True):
    proc = subprocess.run(args, cwd=cwd, input=input_text, env=env, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and proc.returncode:
        raise AssertionError(f"command failed: {args}\nstdout={proc.stdout}\nstderr={proc.stderr}")
    return proc


class AdapterContractTests(unittest.TestCase):
    def make_repo(self):
        td = tempfile.TemporaryDirectory()
        repo = pathlib.Path(td.name) / "repo"
        repo.mkdir()
        command(["git", "-C", str(repo), "init", "-q"])
        command(["git", "-C", str(repo), "config", "user.email", "test@example.com"])
        command(["git", "-C", str(repo), "config", "user.name", "Test"])
        (repo / "README.md").write_text("initial\n")
        command(["git", "-C", str(repo), "add", "README.md"])
        command(["git", "-C", str(repo), "commit", "-q", "-m", "init"])
        command([sys.executable, str(CTX), "--cwd", str(repo), "init", "--checkpoint-gate", "changed-work"])
        return td, repo

    def hook(self, host, event, payload):
        return command([sys.executable, str(CTX), "hook", event, "--host", host], input_text=json.dumps(payload))

    def test_native_startup_output_contracts(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        cursor = json.loads(self.hook("cursor", "session-start", {"session_id": "cursor-1", "cwd": str(repo)}).stdout)
        self.assertIn("additional_context", cursor)
        self.assertEqual(cursor["env"]["PROJECT_CONTEXT_AGENT"], "cursor")
        droid = json.loads(self.hook("droid", "session-start", {"session_id": "droid-1", "cwd": str(repo)}).stdout)
        self.assertIn("additionalContext", droid["hookSpecificOutput"])
        antigravity = json.loads(self.hook("antigravity", "pre-invocation", {
            "conversationId": "agy-1", "workspacePaths": [str(repo)], "invocationNum": 0
        }).stdout)
        self.assertEqual(antigravity["injectSteps"][0].keys(), {"ephemeralMessage"})

    def test_stop_outputs_are_host_native(self):
        for host, expected_key, expected_value in [
            ("codex", "decision", "block"),
            ("cursor", "followup_message", None),
            ("droid", "decision", "block"),
            ("antigravity", "decision", "continue"),
        ]:
            with self.subTest(host=host):
                td, repo = self.make_repo()
                try:
                    session = f"{host}-stop"
                    self.hook(host, "session-start", {"session_id": session, "cwd": str(repo)})
                    self.hook(host, "turn-start", {"session_id": session, "cwd": str(repo)})
                    (repo / "README.md").write_text(f"changed by {host}\n")
                    result = json.loads(self.hook(host, "stop", {"session_id": session, "cwd": str(repo), "fullyIdle": True}).stdout)
                    self.assertIn(expected_key, result)
                    if expected_value is not None:
                        self.assertEqual(result[expected_key], expected_value)
                    else:
                        self.assertIn("checkpoint", result[expected_key].lower())
                finally:
                    td.cleanup()

    def test_generated_adapters_have_required_contract_markers(self):
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            repo = base / "repo"
            home = base / "home"
            repo.mkdir(); home.mkdir()
            command(["git", "-C", str(repo), "init", "-q"])
            env = os.environ.copy(); env["HOME"] = str(home)
            command([sys.executable, str(INSTALL), "hooks", "--hosts", "opencode,pi,hermes,openclaw",
                     "--scope", "project", "--project-root", str(repo)], env=env)
            opencode = (repo / ".opencode/plugins/project-context.js").read_text()
            self.assertIn("experimental.session.compacting", opencode)
            self.assertTrue((repo / ".opencode/commands/project-context.md").exists())
            pi = (repo / ".pi/extensions/project-context.ts").read_text()
            self.assertIn("before_agent_start", pi)
            self.assertIn("agent_settled", pi)
            hermes = (repo / ".hermes/plugins/project-context/__init__.py").read_text()
            compile(hermes, "project-context-hermes", "exec")
            openclaw = (repo / "hooks/project-context/handler.js").read_text()
            self.assertIn('import { homedir } from "node:os"', openclaw)
            if shutil.which("node"):
                command(["node", "--check", str(repo / ".opencode/plugins/project-context.js")])
                command(["node", "--check", str(repo / "hooks/project-context/handler.js")])


if __name__ == "__main__":
    unittest.main()
