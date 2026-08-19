import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
CTX = ROOT / "scripts" / "ctx.py"


def run(args, cwd=None, input_text=None, check=True):
    proc = subprocess.run(
        [sys.executable, str(CTX), *args],
        cwd=cwd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        raise AssertionError(f"command failed: {args}\nstdout={proc.stdout}\nstderr={proc.stderr}")
    return proc


def git(repo, *args):
    proc = subprocess.run(["git", "-C", str(repo), *args], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr)
    return proc.stdout.strip()


class ProjectContextTests(unittest.TestCase):
    def make_repo(self, stop_check=False):
        td = tempfile.TemporaryDirectory()
        repo = pathlib.Path(td.name)
        git(repo, "init", "-q")
        git(repo, "config", "user.email", "test@example.com")
        git(repo, "config", "user.name", "Test")
        (repo / "README.md").write_text("hello\n")
        git(repo, "add", "README.md")
        git(repo, "commit", "-q", "-m", "init")
        args = ["--cwd", str(repo), "init"]
        if stop_check:
            args.append("--stop-check")
        run(args)
        return td, repo

    def test_append_validate_and_query(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        (repo / "README.md").write_text("hello\nchanged\n")
        payload = {
            "record_type": "observation",
            "importance": "high",
            "scope": ["docs"],
            "context": "Updated the project overview after discovering a durable documentation requirement.",
            "attempts": [
                {
                    "approach": "Keep the old wording",
                    "outcome": "failed",
                    "reason": "It omitted the required behavior.",
                    "learning": "The overview must state the behavior explicitly."
                }
            ],
            "learnings": [
                {"type": "constraint", "statement": "The overview must describe the behavior.", "confidence": "confirmed"}
            ]
        }
        proc = run(["--cwd", str(repo), "append", "--agent", "codex", "--input", "-"], input_text=json.dumps(payload))
        result = json.loads(proc.stdout)
        self.assertEqual(result["record_type"], "observation")

        valid = run(["--cwd", str(repo), "validate"])
        self.assertIn("valid: 1 entries", valid.stdout)

        attempts = run(["--cwd", str(repo), "attempts", "--scope", "docs", "--outcome", "failed"])
        self.assertIn("Keep the old wording", attempts.stdout)
        self.assertIn("overview must state", attempts.stdout)

        raw = (repo / ".agent" / "PROJECT_CONTEXT.jsonl").read_text().strip()
        entry = json.loads(raw)
        self.assertEqual(entry["version"], 1)
        self.assertEqual(entry["agent"]["name"], "codex")
        self.assertTrue(any(f["path"] == "README.md" for f in entry["changes"]["files"]))

    def test_reflection_and_startup(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        obs = {
            "record_type": "observation",
            "importance": "high",
            "scope": ["auth"],
            "context": "Found that immediate token invalidation fails under legitimate concurrent refresh requests.",
            "attempts": [{"approach": "Immediate invalidation", "outcome": "failed", "reason": "Concurrent refresh becomes false replay."}]
        }
        run(["--cwd", str(repo), "append", "--agent", "codex", "--input", "-"], input_text=json.dumps(obs))
        reflection = {
            "importance": "high",
            "scope": ["auth"],
            "context": "Authentication now uses bounded previous-token grace because strict immediate invalidation was disproven by concurrent client behavior.",
            "durable_state": {
                "architecture": ["Refresh rotation uses bounded previous-token grace."],
                "known_failed_approaches": ["Immediate invalidation."],
                "open_work": ["Confirm distributed storage strategy."]
            },
            "current_state": {"status": "in_progress", "next_steps": ["Inspect deployment topology."]}
        }
        run(["--cwd", str(repo), "reflect", "--agent", "claude", "--input", "-"], input_text=json.dumps(reflection))
        startup = run(["--cwd", str(repo), "context", "--scope", "auth"])
        self.assertIn("DURABLE REFLECTION", startup.stdout)
        self.assertIn("bounded previous-token grace", startup.stdout)

        entries = [json.loads(x) for x in (repo / ".agent" / "PROJECT_CONTEXT.jsonl").read_text().splitlines()]
        self.assertEqual(entries[-1]["record_type"], "reflection")
        self.assertIn("through_entry_id", entries[-1]["coverage"])

    def test_stop_hook_blocks_until_checkpoint(self):
        td, repo = self.make_repo(stop_check=True)
        self.addCleanup(td.cleanup)
        session = "session-test-1"
        start_input = json.dumps({"session_id": session, "cwd": str(repo), "source": "startup", "hook_event_name": "SessionStart"})
        run(["hook", "session-start", "--host", "codex"], input_text=start_input)
        turn_input = json.dumps({"session_id": session, "cwd": str(repo), "turn_id": "turn-1", "hook_event_name": "UserPromptSubmit"})
        run(["hook", "turn-start", "--host", "codex"], input_text=turn_input)

        (repo / "README.md").write_text("changed by turn\n")
        stop_input = json.dumps({"session_id": session, "cwd": str(repo), "turn_id": "turn-1", "hook_event_name": "Stop", "stop_hook_active": False})
        stop = run(["hook", "stop", "--host", "codex"], input_text=stop_input)
        decision = json.loads(stop.stdout)
        self.assertEqual(decision.get("decision"), "block")

        payload = {
            "record_type": "observation",
            "importance": "medium",
            "scope": ["docs"],
            "context": "Changed README content for the current task and checkpointed the resulting repository state."
        }
        run(["--cwd", str(repo), "append", "--agent", "codex", "--input", "-"], input_text=json.dumps(payload))
        stop2 = run(["hook", "stop", "--host", "codex"], input_text=stop_input)
        self.assertEqual(json.loads(stop2.stdout), {})


if __name__ == "__main__":
    unittest.main()
