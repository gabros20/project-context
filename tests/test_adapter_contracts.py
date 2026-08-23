import json
import io
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from scripts import ctx as ctx_module

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
        command(["git", "-C", str(repo), "config", "commit.gpgsign", "false"])
        (repo / "README.md").write_text("initial\n")
        command(["git", "-C", str(repo), "add", "README.md"])
        command(["git", "-C", str(repo), "commit", "-q", "-m", "init"])
        command([sys.executable, str(CTX), "--cwd", str(repo), "init", "--checkpoint-gate", "changed-work"])
        return td, repo

    def hook(self, host, event, payload):
        env = os.environ.copy()
        cwd = payload.get("cwd") or (payload.get("workspacePaths") or [ROOT])[0]
        env["XDG_CACHE_HOME"] = str(pathlib.Path(cwd).parent / "cache")
        return command([sys.executable, str(CTX), "hook", event, "--host", host], input_text=json.dumps(payload), env=env)

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

    def test_startup_only_generated_adapters_omit_turn_and_stop_work(self):
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            repo = base / "repo"
            home = base / "home"
            repo.mkdir(); home.mkdir()
            command(["git", "-C", str(repo), "init", "-q"])
            env = os.environ.copy(); env["HOME"] = str(home)
            command([sys.executable, str(INSTALL), "hooks", "--hosts", "opencode,pi,hermes,openclaw",
                     "--scope", "project", "--project-root", str(repo), "--hook-profile", "startup-only"], env=env)

            opencode = (repo / ".opencode/plugins/project-context.js").read_text()
            self.assertIn("hook profile: startup-only", opencode)
            self.assertNotIn("session.idle", opencode)
            self.assertIn("experimental.session.compacting", opencode)
            pi = (repo / ".pi/extensions/project-context.ts").read_text()
            self.assertNotIn('run("turn-start"', pi)
            self.assertNotIn("agent_settled", pi)
            self.assertIn("session_compact", pi)
            hermes = (repo / ".hermes/plugins/project-context/__init__.py").read_text()
            self.assertNotIn('_run("turn-start"', hermes)
            self.assertNotIn('register_hook("pre_verify"', hermes)
            compile(hermes, "project-context-hermes-startup-only", "exec")
            hook_md = (repo / "hooks/project-context/HOOK.md").read_text()
            self.assertNotIn("session:compact:before", hook_md)
            openclaw = (repo / "hooks/project-context/handler.js").read_text()
            self.assertNotIn("compact-before", openclaw)
            status = command([sys.executable, str(INSTALL), "status", "--hosts", "opencode,pi,hermes,openclaw",
                              "--scope", "project", "--project-root", str(repo)], env=env)
            self.assertEqual(status.stdout.count("profile=startup-only"), 4)
            if shutil.which("node"):
                command(["node", "--check", str(repo / ".opencode/plugins/project-context.js")])
                command(["node", "--check", str(repo / "hooks/project-context/handler.js")])

    def test_startup_and_turn_start_do_not_fingerprint_when_gate_is_off(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        config_path = repo / ".agent/project-context.json"
        config = json.loads(config_path.read_text())
        config["checkpoint"]["stop_gate"] = "off"
        config_path.write_text(json.dumps(config))
        output = io.StringIO()
        with mock.patch.dict(os.environ, {"XDG_CACHE_HOME": str(repo.parent / "cache")}):
            with mock.patch.object(ctx_module, "git_fingerprint", side_effect=AssertionError("unexpected Git fingerprint")):
                with redirect_stdout(output):
                    start_result = ctx_module.hook_session_start("cursor", {"session_id": "cursor-fast", "cwd": str(repo)})
                    result = ctx_module.hook_turn_start("cursor", {"session_id": "cursor-fast", "cwd": str(repo)})
        self.assertEqual(start_result, 0)
        self.assertEqual(result, 0)
        lines = output.getvalue().splitlines()
        self.assertIn("additional_context", json.loads(lines[0]))
        self.assertEqual(json.loads(lines[1]), {"continue": True})


if __name__ == "__main__":
    unittest.main()
