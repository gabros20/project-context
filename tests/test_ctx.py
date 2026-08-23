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
        self.assertEqual(startup.stdout.count("Authentication now uses bounded previous-token grace"), 1)

    def test_reflection_coverage_is_scoped_and_path_retrievable(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        auth = {
            "record_type": "observation", "importance": "high", "scope": ["auth"],
            "related_paths": ["src/auth/session.ts"],
            "context": "Auth requires a bounded refresh-token grace period."
        }
        docs = {
            "record_type": "observation", "importance": "medium", "scope": ["docs"],
            "context": "The installation guide now explains local setup."
        }
        run(["--cwd", str(repo), "append", "--agent", "codex", "--input", "-"], input_text=json.dumps(auth))
        run(["--cwd", str(repo), "append", "--agent", "codex", "--input", "-"], input_text=json.dumps(docs))
        docs_reflection = {
            "importance": "high", "scope": ["docs"], "context": "Documentation setup guidance is durable.",
            "durable_state": {"completed": ["Documented local setup."]}
        }
        run(["--cwd", str(repo), "reflect", "--agent", "claude", "--input", "-"], input_text=json.dumps(docs_reflection))
        auth_context = run(["--cwd", str(repo), "context", "--scope", "auth"])
        self.assertIn("bounded refresh-token grace", auth_context.stdout)
        self.assertNotIn("Documentation setup guidance", auth_context.stdout)

        auth_reflection = {
            "importance": "high", "scope": ["auth"], "context": "Bounded refresh-token grace is the durable auth design.",
            "durable_state": {"architecture": ["Refresh rotation permits bounded previous-token grace."]}
        }
        run(["--cwd", str(repo), "reflect", "--agent", "claude", "--input", "-"], input_text=json.dumps(auth_reflection))
        by_path = run(["--cwd", str(repo), "context", "--path", "src/auth/session.ts", "--explain"])
        self.assertIn("DURABLE REFLECTION", by_path.stdout)
        self.assertIn("relevant-reflection", by_path.stdout)

    def test_budget_preserves_latest_handoff(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        for index in range(8):
            payload = {
                "record_type": "observation", "importance": "high", "scope": ["core"],
                "context": f"Older high-priority record {index}: " + ("detail " * 120)
            }
            run(["--cwd", str(repo), "append", "--agent", "codex", "--input", "-"], input_text=json.dumps(payload))
        handoff = {
            "importance": "medium", "scope": ["core"], "context": "LATEST HANDOFF MUST SURVIVE",
            "current_state": {"status": "in_progress", "next_steps": ["Continue from the parser boundary."]}
        }
        run(["--cwd", str(repo), "handoff", "--agent", "codex", "--input", "-"], input_text=json.dumps(handoff))
        packet = run(["--cwd", str(repo), "context", "--scope", "core", "--budget", "300"])
        self.assertIn("LATEST HANDOFF MUST SURVIVE", packet.stdout)

    def test_nested_validation_rejects_invalid_records(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        invalid = {
            "record_type": "observation", "scope": ["core"], "context": "Invalid nested data.",
            "decisions": [{}], "changes": {"files": [{"path": "../outside", "operation": "rewritten"}]}
        }
        proc = run(["--cwd", str(repo), "append", "--agent", "codex", "--input", "-"], input_text=json.dumps(invalid), check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("decision requires", proc.stderr)
        self.assertIn("repository-relative path", proc.stderr)

    def test_every_turn_due_can_be_satisfied_by_skip(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        run(["--cwd", str(repo), "init", "--checkpoint-gate", "every-turn", "--force"])
        session = "every-turn-session"
        start = json.dumps({"session_id": session, "cwd": str(repo)})
        run(["hook", "session-start", "--host", "codex"], input_text=start)
        run(["hook", "turn-start", "--host", "codex"], input_text=start)
        due = run(["--cwd", str(repo), "due", "--agent", "codex", "--session-id", session, "--json"], check=False)
        self.assertEqual(due.returncode, 1)
        self.assertTrue(json.loads(due.stdout)["due"])
        run(["--cwd", str(repo), "skip", "--agent", "codex", "--session-id", session, "--reason", "No durable result."])
        satisfied = run(["--cwd", str(repo), "due", "--agent", "codex", "--session-id", session, "--json"])
        self.assertFalse(json.loads(satisfied.stdout)["due"])

    def test_git_common_storage_places_log_outside_worktree(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        run(["--cwd", str(repo), "init", "--storage", "git-common", "--force"])
        payload = {"record_type": "observation", "scope": ["core"], "context": "Stored in the common Git directory."}
        run(["--cwd", str(repo), "append", "--agent", "codex", "--input", "-"], input_text=json.dumps(payload))
        common = pathlib.Path(git(repo, "rev-parse", "--git-common-dir"))
        if not common.is_absolute():
            common = repo / common
        self.assertTrue((common / "project-context" / "PROJECT_CONTEXT.jsonl").exists())

    def test_storage_policy_is_explicit_and_safe(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        run(["--cwd", str(repo), "init", "--tracking", "ignored", "--force"])
        ignore = (repo / ".gitignore").read_text()
        self.assertIn("project-context-storage:begin", ignore)
        self.assertIn("/.agent/PROJECT_CONTEXT.jsonl", ignore)
        invalid = run(["--cwd", str(repo), "init", "--storage", "external", "--storage-path", "relative/log.jsonl", "--force"], check=False)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertIn("absolute", invalid.stderr)

    def test_custom_repo_ledger_is_not_captured_as_changed_work(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        run([
            "--cwd", str(repo), "init", "--storage", "repo",
            "--storage-path", ".context/events.jsonl", "--force"
        ])
        (repo / "README.md").write_text("durable user change\n")
        payload = {
            "record_type": "observation", "scope": ["core"],
            "context": "Captured a real user change without treating the ledger as project work."
        }
        run(
            ["--cwd", str(repo), "append", "--agent", "codex", "--input", "-"],
            input_text=json.dumps(payload),
        )
        entry = json.loads((repo / ".context" / "events.jsonl").read_text().strip())
        changed_paths = [item["path"] for item in entry["changes"]["files"]]
        self.assertIn("README.md", changed_paths)
        self.assertNotIn(".context/events.jsonl", changed_paths)

    def test_legacy_stop_check_config_migrates_in_memory(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        cfg_path = repo / ".agent" / "project-context.json"
        cfg = json.loads(cfg_path.read_text())
        cfg.pop("checkpoint", None)
        cfg["hooks"] = {"stop_check": True}
        cfg_path.write_text(json.dumps(cfg))
        doctor = run(["--cwd", str(repo), "doctor"])
        self.assertIn("checkpoint_stop_gate: changed-work", doctor.stdout)

    def test_concurrent_appends_do_not_corrupt_jsonl(self):
        td, repo = self.make_repo()
        self.addCleanup(td.cleanup)
        processes = []
        for index in range(20):
            payload = json.dumps({
                "record_type": "observation", "scope": ["concurrency"],
                "context": f"Concurrent durable record {index}."
            })
            processes.append(subprocess.Popen(
                [sys.executable, str(CTX), "--cwd", str(repo), "append", "--agent", "worker", "--input", "-"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            ))
            processes[-1].stdin.write(payload)
            processes[-1].stdin.close()
        for process in processes:
            stdout = process.stdout.read()
            stderr = process.stderr.read()
            process.stdout.close()
            process.stderr.close()
            self.assertEqual(process.wait(), 0, f"stdout={stdout}\nstderr={stderr}")
        validated = run(["--cwd", str(repo), "validate"])
        self.assertIn("valid: 20 entries", validated.stdout)

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
