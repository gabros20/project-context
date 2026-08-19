#!/usr/bin/env python3
"""project-context CLI.

Standard-library-only append/query/lifecycle utility for shared coding-agent memory.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import uuid
from typing import Any, Iterable

PROTOCOL_VERSION = 1
PACKAGE_VERSION = "0.3.0"
RECORD_TYPES = {"observation", "reflection", "handoff"}
IMPORTANCE = {"low", "medium", "high", "critical"}
ATTEMPT_OUTCOMES = {"worked", "failed", "partial", "inconclusive", "abandoned"}
LEARNING_TYPES = {"fact", "invariant", "constraint", "convention", "gotcha", "hypothesis", "open_question"}
CONFIDENCE = {"confirmed", "likely", "tentative"}
VERIFY_OUTCOMES = {"passed", "failed", "partial", "not_run", "inconclusive"}
IMPORTANCE_WEIGHT = {"low": 0, "medium": 1, "high": 2, "critical": 3}

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "enabled": True,
    "log": ".agent/PROJECT_CONTEXT.jsonl",
    "schema_copy": ".agent/PROJECT_CONTEXT.schema.json",
    "startup": {
        "latest_without_reflection": 6,
        "token_budget": 2200,
        "compact_token_budget": 1200,
    },
    "retrieval": {"latest": 10, "token_budget": 3000},
    "reflection": {"suggest_after_observations": 20},
    "hooks": {"stop_check": False},
    "scopes": [],
}


class ContextError(RuntimeError):
    pass


def eprint(*args: Any) -> None:
    print(*args, file=sys.stderr)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> dt.datetime:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContextError(f"invalid RFC3339 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def run_git(root: pathlib.Path, *args: str, check: bool = False) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if check and proc.returncode != 0:
        raise ContextError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout.strip() if proc.returncode == 0 else ""


def discover_repo(cwd: str | pathlib.Path | None = None) -> pathlib.Path | None:
    base = pathlib.Path(cwd or os.getcwd()).expanduser().resolve()
    proc = subprocess.run(
        ["git", "-C", str(base), "rev-parse", "--show-toplevel"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return pathlib.Path(proc.stdout.strip()).resolve()


def skill_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def config_path(root: pathlib.Path) -> pathlib.Path:
    return root / ".agent" / "project-context.json"


def load_config(root: pathlib.Path, require_enabled: bool = True) -> dict[str, Any] | None:
    path = config_path(root)
    log_fallback = root / ".agent" / "PROJECT_CONTEXT.jsonl"
    if not path.exists() and not log_fallback.exists():
        return None
    override: dict[str, Any] = {}
    if path.exists():
        try:
            override = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ContextError(f"cannot read {path}: {exc}") from exc
    cfg = deep_merge(DEFAULT_CONFIG, override)
    if require_enabled and not cfg.get("enabled", True):
        return None
    return cfg


def log_path(root: pathlib.Path, cfg: dict[str, Any]) -> pathlib.Path:
    raw = pathlib.Path(str(cfg.get("log", DEFAULT_CONFIG["log"])))
    return raw if raw.is_absolute() else root / raw


def cache_root() -> pathlib.Path:
    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        path = pathlib.Path(base).expanduser() / "project-context"
    elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
        path = pathlib.Path(os.environ["LOCALAPPDATA"]) / "project-context"
    else:
        path = pathlib.Path.home() / ".cache" / "project-context"
    path.mkdir(parents=True, exist_ok=True)
    return path


def repo_key(root: pathlib.Path) -> str:
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:20]


def runtime_dir(root: pathlib.Path) -> pathlib.Path:
    path = cache_root() / "runtime" / repo_key(root)
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value)[:180] or "unknown"


def session_state_path(root: pathlib.Path, session_id: str) -> pathlib.Path:
    return runtime_dir(root) / f"session-{safe_id(session_id)}.json"


def active_pointer_path(root: pathlib.Path, host: str) -> pathlib.Path:
    return runtime_dir(root) / f"active-{safe_id(host)}.json"


def read_json(path: pathlib.Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json_atomic(path: pathlib.Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)


def current_git_info(root: pathlib.Path) -> dict[str, Any]:
    head = run_git(root, "rev-parse", "HEAD") or "unborn"
    branch = run_git(root, "branch", "--show-current") or run_git(root, "rev-parse", "--abbrev-ref", "HEAD") or "detached"
    status = filtered_git_status(root)
    return {
        "name": root.name,
        "branch": branch,
        "worktree": root.name,
        "head_commit": head,
        "dirty": bool(status),
    }


def git_status_raw(root: pathlib.Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return proc.stdout if proc.returncode == 0 else ""


def coordination_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized in {
        ".agent/PROJECT_CONTEXT.jsonl",
        ".agent/PROJECT_CONTEXT.schema.json",
        ".agent/project-context.json",
    }


def filtered_git_status(root: pathlib.Path) -> str:
    kept = []
    for line in git_status_raw(root).splitlines():
        path = line[3:] if len(line) >= 4 else ""
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if coordination_path(path):
            continue
        kept.append(line)
    return "\n".join(kept)


def git_fingerprint(root: pathlib.Path) -> str:
    head = run_git(root, "rev-parse", "HEAD") or "unborn"
    payload = head + "\n" + filtered_git_status(root)
    return hashlib.sha256(payload.encode("utf-8", errors="replace")).hexdigest()


def detect_changed_files(root: pathlib.Path) -> list[dict[str, Any]]:
    raw = git_status_raw(root)
    out: list[dict[str, Any]] = []
    if not raw:
        return out
    for line in raw.splitlines():
        if len(line) < 4:
            continue
        status = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if coordination_path(path):
            continue
        if status == "??":
            operation = "untracked"
        elif "R" in status:
            operation = "renamed"
        elif "C" in status:
            operation = "copied"
        elif "D" in status:
            operation = "deleted"
        elif "A" in status:
            operation = "added"
        elif "M" in status:
            operation = "modified"
        else:
            operation = "unknown"
        out.append({"path": path, "operation": operation})
    return out


def load_entries(root: pathlib.Path, cfg: dict[str, Any], strict: bool = True) -> list[dict[str, Any]]:
    path = log_path(root, cfg)
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                if strict:
                    raise ContextError(f"malformed JSONL at {path}:{lineno}: {exc}") from exc
                continue
            if not isinstance(obj, dict):
                if strict:
                    raise ContextError(f"non-object JSONL record at {path}:{lineno}")
                continue
            entries.append(obj)
    return entries


def validate_semantic(payload: dict[str, Any], record_type_override: str | None = None) -> list[str]:
    errors: list[str] = []
    record_type = record_type_override or payload.get("record_type")
    if record_type not in RECORD_TYPES:
        errors.append(f"record_type must be one of {sorted(RECORD_TYPES)}")
    importance = payload.get("importance", "medium")
    if importance not in IMPORTANCE:
        errors.append(f"importance must be one of {sorted(IMPORTANCE)}")
    scope = payload.get("scope")
    if scope is None:
        errors.append("scope is required (use [] only for truly project-wide records)")
    elif not isinstance(scope, list) or not all(isinstance(x, str) and x.strip() for x in scope):
        errors.append("scope must be an array of non-empty strings")
    context = payload.get("context")
    if not isinstance(context, str) or not context.strip():
        errors.append("context is required and must be non-empty")
    for attempt in payload.get("attempts", []) or []:
        if not isinstance(attempt, dict):
            errors.append("attempts entries must be objects")
            continue
        if attempt.get("outcome") not in ATTEMPT_OUTCOMES:
            errors.append(f"attempt outcome must be one of {sorted(ATTEMPT_OUTCOMES)}")
    for learning in payload.get("learnings", []) or []:
        if not isinstance(learning, dict):
            errors.append("learnings entries must be objects")
            continue
        if learning.get("type") not in LEARNING_TYPES:
            errors.append(f"learning type must be one of {sorted(LEARNING_TYPES)}")
        if learning.get("confidence") not in CONFIDENCE:
            errors.append(f"learning confidence must be one of {sorted(CONFIDENCE)}")
    for check in payload.get("verification", []) or []:
        if isinstance(check, dict) and check.get("outcome") not in VERIFY_OUTCOMES:
            errors.append(f"verification outcome must be one of {sorted(VERIFY_OUTCOMES)}")
    if record_type == "handoff" and not isinstance(payload.get("current_state"), dict):
        errors.append("handoff requires current_state")
    if record_type == "reflection":
        if not isinstance(payload.get("durable_state"), dict):
            errors.append("reflection requires durable_state")
        if payload.get("coverage") is not None and not isinstance(payload.get("coverage"), dict):
            errors.append("reflection coverage must be an object")
    return errors


def validate_entry(entry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = ["version", "timestamp", "entry_id", "record_type", "importance", "agent", "repository", "scope", "context"]
    for key in required:
        if key not in entry:
            errors.append(f"missing required field: {key}")
    if entry.get("version") != PROTOCOL_VERSION:
        errors.append(f"unsupported version: {entry.get('version')}")
    try:
        if "timestamp" in entry:
            parse_timestamp(str(entry["timestamp"]))
    except ContextError as exc:
        errors.append(str(exc))
    errors.extend(validate_semantic(entry))
    agent = entry.get("agent")
    if not isinstance(agent, dict) or not agent.get("name") or not agent.get("session_id"):
        errors.append("agent requires name and session_id")
    repo = entry.get("repository")
    if not isinstance(repo, dict):
        errors.append("repository must be an object")
    else:
        for key in ["name", "branch", "worktree", "head_commit", "dirty"]:
            if key not in repo:
                errors.append(f"repository missing {key}")
    if entry.get("record_type") == "reflection" and not isinstance(entry.get("coverage"), dict):
        errors.append("reflection requires coverage")
    return errors


def lock_path_for(log: pathlib.Path) -> pathlib.Path:
    locks = cache_root() / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(log.resolve()).encode()).hexdigest()
    return locks / f"{key}.lock"


@contextlib.contextmanager
def file_lock(log: pathlib.Path):
    lock_path = lock_path_for(log)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = lock_path.open("a+b")
    try:
        if os.name == "nt":
            import msvcrt  # type: ignore

            fh.seek(0)
            if fh.tell() == 0:
                fh.write(b"0")
                fh.flush()
            fh.seek(0)
            msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl  # type: ignore

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        if os.name == "nt":
            import msvcrt  # type: ignore

            fh.seek(0)
            with contextlib.suppress(OSError):
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl  # type: ignore

            with contextlib.suppress(OSError):
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()


def append_entry(root: pathlib.Path, cfg: dict[str, Any], entry: dict[str, Any]) -> None:
    errors = validate_entry(entry)
    if errors:
        raise ContextError("invalid entry:\n- " + "\n- ".join(errors))
    path = log_path(root, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
    with file_lock(path):
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())


def active_session(root: pathlib.Path, agent: str) -> dict[str, Any] | None:
    pointer = read_json(active_pointer_path(root, agent))
    if not isinstance(pointer, dict) or not pointer.get("session_id"):
        return None
    state = read_json(session_state_path(root, str(pointer["session_id"])))
    return state if isinstance(state, dict) else None


def update_runtime_after_checkpoint(root: pathlib.Path, agent: str, session_id: str, entry_id: str) -> None:
    state_path = session_state_path(root, session_id)
    state = read_json(state_path, {}) or {}
    state.update(
        {
            "session_id": session_id,
            "host": state.get("host", agent),
            "last_event_at": utc_now(),
            "last_event_id": entry_id,
            "last_event_fingerprint": git_fingerprint(root),
        }
    )
    write_json_atomic(state_path, state)
    write_json_atomic(active_pointer_path(root, agent), {"session_id": session_id, "updated_at": utc_now()})


def resolve_session_id(root: pathlib.Path, agent: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    env_value = os.environ.get("PROJECT_CONTEXT_SESSION_ID")
    if env_value:
        return env_value
    state = active_session(root, agent)
    if state and state.get("session_id"):
        return str(state["session_id"])
    return f"manual-{dt.datetime.now().strftime('%Y%m%d')}"


def auto_changes(root: pathlib.Path, payload: dict[str, Any]) -> None:
    detected = detect_changed_files(root)
    if not detected:
        return
    changes = payload.setdefault("changes", {})
    if not isinstance(changes, dict):
        return
    if not changes.get("files"):
        changes["files"] = detected


def reflection_coverage(entries: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    coverage = payload.setdefault("coverage", {})
    if not isinstance(coverage, dict):
        payload["coverage"] = coverage = {}
    if not entries:
        coverage.setdefault("supporting_entry_ids", [])
        return
    previous_reflection_idx = -1
    for i, entry in enumerate(entries):
        if entry.get("record_type") == "reflection":
            previous_reflection_idx = i
    start_idx = previous_reflection_idx + 1
    coverage.setdefault("from_entry_id", entries[start_idx].get("entry_id") if start_idx < len(entries) else entries[-1].get("entry_id"))
    coverage.setdefault("through_entry_id", entries[-1].get("entry_id"))
    coverage.setdefault("supporting_entry_ids", [e.get("entry_id") for e in entries[start_idx:] if e.get("entry_id")][-20:])


def build_entry(
    root: pathlib.Path,
    cfg: dict[str, Any],
    payload: dict[str, Any],
    agent: str,
    session_id: str | None,
    record_type_override: str | None = None,
) -> dict[str, Any]:
    payload = json.loads(json.dumps(payload))
    if record_type_override:
        payload["record_type"] = record_type_override
    payload.setdefault("importance", "medium")
    errors = validate_semantic(payload, record_type_override)
    if errors:
        raise ContextError("invalid semantic payload:\n- " + "\n- ".join(errors))
    if payload.get("record_type") == "reflection":
        reflection_coverage(load_entries(root, cfg), payload)
    if payload.get("record_type") in {"observation", "handoff"}:
        auto_changes(root, payload)
    sid = resolve_session_id(root, agent, session_id)
    entry: dict[str, Any] = {
        "version": PROTOCOL_VERSION,
        "timestamp": utc_now(),
        "entry_id": str(uuid.uuid4()),
        "record_type": payload.pop("record_type"),
        "importance": payload.pop("importance"),
        "agent": {"name": agent, "session_id": sid},
        "repository": current_git_info(root),
        "scope": sorted(set(payload.pop("scope"))),
        "context": payload.pop("context").strip(),
    }
    # Strip empty optional sections so storage stays clean.
    for key, value in payload.items():
        if value is None or value == [] or value == {} or value == "":
            continue
        entry[key] = value
    return entry


def read_payload(args: argparse.Namespace, record_type: str | None = None) -> dict[str, Any]:
    if getattr(args, "input", None):
        if args.input == "-":
            raw = sys.stdin.read()
        else:
            raw = pathlib.Path(args.input).read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContextError(f"invalid input JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ContextError("input JSON must be an object")
    else:
        data = {}
        if getattr(args, "context", None):
            data["context"] = args.context
        scopes = getattr(args, "scope", None)
        if scopes is not None:
            data["scope"] = scopes
        if getattr(args, "importance", None):
            data["importance"] = args.importance
        tags = getattr(args, "tag", None)
        if tags:
            data["tags"] = tags
    if record_type:
        data["record_type"] = record_type
    return data


def entry_timestamp(entry: dict[str, Any]) -> dt.datetime:
    try:
        return parse_timestamp(str(entry.get("timestamp", "1970-01-01T00:00:00Z")))
    except ContextError:
        return dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


def matches_scope(entry: dict[str, Any], scopes: list[str] | None) -> bool:
    if not scopes:
        return True
    entry_scopes = {str(x).lower() for x in entry.get("scope", []) if isinstance(x, str)}
    return bool(entry_scopes.intersection({x.lower() for x in scopes}))


def entry_paths(entry: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    changes = entry.get("changes", {})
    if isinstance(changes, dict):
        for file in changes.get("files", []) or []:
            if isinstance(file, dict) and isinstance(file.get("path"), str):
                paths.append(file["path"])
        for artifact in changes.get("artifacts", []) or []:
            if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
                paths.append(artifact["path"])
    return paths


def matches_path(entry: dict[str, Any], path_query: str | None) -> bool:
    if not path_query:
        return True
    q = path_query.replace("\\", "/").lower().rstrip("/")
    for path in entry_paths(entry):
        p = path.replace("\\", "/").lower()
        if p == q or p.startswith(q + "/") or q.startswith(p.rstrip("/") + "/") or q in p:
            return True
    return False


def filter_entries(
    entries: Iterable[dict[str, Any]],
    scopes: list[str] | None = None,
    path_query: str | None = None,
    agent: str | None = None,
    record_type: str | None = None,
    since: str | None = None,
    minimum_importance: str | None = None,
) -> list[dict[str, Any]]:
    since_dt = parse_timestamp(since) if since else None
    min_weight = IMPORTANCE_WEIGHT.get(minimum_importance or "low", 0)
    out: list[dict[str, Any]] = []
    for entry in entries:
        if not matches_scope(entry, scopes) or not matches_path(entry, path_query):
            continue
        if agent and str(entry.get("agent", {}).get("name", "")).lower() != agent.lower():
            continue
        if record_type and entry.get("record_type") != record_type:
            continue
        if since_dt and entry_timestamp(entry) <= since_dt:
            continue
        if IMPORTANCE_WEIGHT.get(str(entry.get("importance", "low")), 0) < min_weight:
            continue
        out.append(entry)
    return out


def list_strings(title: str, values: Any, indent: str = "  ") -> list[str]:
    if not isinstance(values, list) or not values:
        return []
    lines = [f"{title}:"]
    for value in values:
        if isinstance(value, str):
            lines.append(f"{indent}- {value}")
    return lines if len(lines) > 1 else []


def format_entry(entry: dict[str, Any], full: bool = False) -> str:
    agent = entry.get("agent", {}).get("name", "unknown")
    scopes = ",".join(entry.get("scope", [])) or "project"
    header = f"[{entry.get('timestamp','?')}] {agent} {entry.get('record_type','?')}/{entry.get('importance','?')} [{scopes}] id={entry.get('entry_id','?')}"
    lines = [header, str(entry.get("context", "")).strip()]

    for decision in entry.get("decisions", []) or []:
        if not isinstance(decision, dict):
            continue
        lines.append(f"DECISION: {decision.get('decision','')}")
        if decision.get("rationale"):
            lines.append(f"  rationale: {decision['rationale']}")
        if full:
            for alt in decision.get("alternatives", []) or []:
                if isinstance(alt, dict):
                    line = f"  alternative: {alt.get('option','')} [{alt.get('outcome','')}]"
                    if alt.get("reason"):
                        line += f" — {alt['reason']}"
                    lines.append(line)

    for attempt in entry.get("attempts", []) or []:
        if not isinstance(attempt, dict):
            continue
        line = f"ATTEMPT[{attempt.get('outcome','?')}]: {attempt.get('approach','')}"
        if attempt.get("reason"):
            line += f" — {attempt['reason']}"
        lines.append(line)
        if full and attempt.get("evidence"):
            lines.append(f"  evidence: {attempt['evidence']}")
        if attempt.get("learning"):
            lines.append(f"  learning: {attempt['learning']}")

    for learning in entry.get("learnings", []) or []:
        if isinstance(learning, dict):
            lines.append(f"LEARNING[{learning.get('type','?')}/{learning.get('confidence','?')}]: {learning.get('statement','')}")

    durable = entry.get("durable_state")
    if isinstance(durable, dict):
        for key in ["architecture", "decisions", "constraints", "known_failed_approaches", "successful_approaches", "completed", "open_work"]:
            values = durable.get(key)
            if values:
                lines.extend(list_strings(f"DURABLE {key.replace('_',' ').upper()}", values))

    current = entry.get("current_state")
    if isinstance(current, dict):
        if current.get("status"):
            lines.append(f"STATE: {current['status']}")
        for key in ["working", "remaining", "blockers", "open_questions", "next_steps"]:
            lines.extend(list_strings(key.replace("_", " ").upper(), current.get(key)))

    verification = entry.get("verification")
    if isinstance(verification, list) and verification:
        for check in verification:
            if isinstance(check, dict):
                line = f"VERIFY[{check.get('outcome','?')}]: {check.get('check','')}"
                if check.get("details"):
                    line += f" — {check['details']}"
                lines.append(line)

    changes = entry.get("changes")
    if isinstance(changes, dict):
        commits = changes.get("commits") or []
        files = changes.get("files") or []
        artifacts = changes.get("artifacts") or []
        if commits:
            lines.append("COMMITS: " + ", ".join(str(x) for x in commits))
        if files:
            parts = []
            for file in files:
                if isinstance(file, dict):
                    piece = f"{file.get('operation','?')}:{file.get('path','?')}"
                    if full and file.get("purpose"):
                        piece += f" ({file['purpose']})"
                    parts.append(piece)
            if parts:
                lines.append("FILES: " + "; ".join(parts))
        if artifacts:
            parts = []
            for artifact in artifacts:
                if isinstance(artifact, dict):
                    piece = str(artifact.get("path", "?"))
                    if full and artifact.get("purpose"):
                        piece += f" ({artifact['purpose']})"
                    parts.append(piece)
            if parts:
                lines.append("ARTIFACTS: " + "; ".join(parts))

    related = entry.get("related_entries")
    if full and isinstance(related, dict):
        for key in ["supersedes", "resolves", "related"]:
            vals = related.get(key)
            if vals:
                lines.append(f"{key.upper()}: " + ", ".join(str(x) for x in vals))

    coverage = entry.get("coverage")
    if isinstance(coverage, dict):
        through = coverage.get("through_entry_id")
        support = coverage.get("supporting_entry_ids") or []
        if through:
            lines.append(f"COVERAGE through={through} support={len(support)}")

    repo = entry.get("repository", {})
    if isinstance(repo, dict):
        lines.append(f"GIT: {repo.get('head_commit','?')} branch={repo.get('branch','?')} dirty={repo.get('dirty','?')}")

    return "\n".join(line for line in lines if line is not None and str(line).strip())


def approx_char_budget(tokens: int) -> int:
    return max(400, int(tokens * 4.0))


def trim_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars < 100:
        return text[:max_chars]
    return text[: max_chars - 40].rstrip() + "\n… [context truncated by budget]"


def blocks_with_budget(blocks: list[str], token_budget: int) -> str:
    max_chars = approx_char_budget(token_budget)
    out: list[str] = []
    used = 0
    for block in blocks:
        sep = 2 if out else 0
        if used + sep + len(block) <= max_chars:
            out.append(block)
            used += sep + len(block)
            continue
        remaining = max_chars - used - sep
        if remaining > 200:
            out.append(trim_text(block, remaining))
        break
    return "\n\n".join(out)


def coverage_index(entries: list[dict[str, Any]], reflection: dict[str, Any]) -> int:
    through = (reflection.get("coverage") or {}).get("through_entry_id") if isinstance(reflection.get("coverage"), dict) else None
    if through:
        for idx, entry in enumerate(entries):
            if entry.get("entry_id") == through:
                return idx
    try:
        return entries.index(reflection)
    except ValueError:
        return -1


def latest_reflection(entries: list[dict[str, Any]], scopes: list[str] | None = None) -> dict[str, Any] | None:
    candidates = [e for e in entries if e.get("record_type") == "reflection" and matches_scope(e, scopes)]
    return candidates[-1] if candidates else None


def select_context_entries(
    entries: list[dict[str, Any]],
    scopes: list[str] | None,
    path_query: str | None,
    latest_without_reflection: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    relevant = filter_entries(entries, scopes=scopes, path_query=path_query)
    reflection = latest_reflection(relevant, scopes)
    if not reflection:
        return relevant[-latest_without_reflection:], None

    idx = coverage_index(entries, reflection)
    tail = entries[idx + 1 :] if idx >= 0 else entries
    tail = filter_entries(tail, scopes=scopes, path_query=path_query)

    high = [e for e in tail if IMPORTANCE_WEIGHT.get(str(e.get("importance", "low")), 0) >= IMPORTANCE_WEIGHT["high"]]
    handoffs = [e for e in tail if e.get("record_type") == "handoff"]
    recent = tail[-latest_without_reflection:]
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in [*high, *handoffs, *recent]:
        eid = str(entry.get("entry_id", id(entry)))
        if eid not in seen:
            selected.append(entry)
            seen.add(eid)
    selected.sort(key=entry_timestamp)
    return selected, reflection


def context_packet(
    root: pathlib.Path,
    cfg: dict[str, Any],
    scopes: list[str] | None = None,
    path_query: str | None = None,
    token_budget: int | None = None,
    compact: bool = False,
) -> str:
    entries = load_entries(root, cfg)
    if not entries:
        return (
            "PROJECT CONTEXT ENABLED\n"
            "No project-context entries exist yet. Use the project-context skill after meaningful durable work; do not create tool-call narration."
        )
    startup_cfg = cfg.get("startup", {})
    default_latest = int(startup_cfg.get("latest_without_reflection", 6))
    if token_budget is None:
        token_budget = int(
            startup_cfg.get("compact_token_budget" if compact else "token_budget", 1200 if compact else 2200)
        )
    selected, reflection = select_context_entries(entries, scopes, path_query, default_latest)
    scope_label = ",".join(scopes or []) or (path_query or "project")
    header = [
        f"PROJECT MEMORY — {scope_label}",
        f"repository: {root.name}",
        f"entries: {len(entries)}",
    ]
    blocks = ["\n".join(header)]
    if reflection:
        blocks.append("DURABLE REFLECTION\n" + format_entry(reflection, full=False))
    if selected:
        blocks.append("RECENT / UNREFLECTED FRONTIER\n" + "\n\n".join(format_entry(e, full=False) for e in selected))
    if not compact:
        blocks.append(
            "USE TARGETED RETRIEVAL IF NEEDED\n"
            "ctx context --scope <scope> | ctx context --path <path> | ctx attempts --outcome failed | ctx decisions | ctx open"
        )
    return blocks_with_budget(blocks, token_budget)


def emit_entries(entries: list[dict[str, Any]], fmt: str, full: bool, token_budget: int | None = None) -> None:
    if fmt == "jsonl":
        for entry in entries:
            print(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
        return
    blocks = [format_entry(e, full=full) for e in entries]
    text = "\n\n".join(blocks)
    if token_budget:
        text = trim_text(text, approx_char_budget(token_budget))
    print(text)


def parse_hook_input() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def first_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                return item
    return None


def hook_cwd(data: dict[str, Any]) -> str:
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    candidates = [
        data.get("cwd"),
        data.get("workspaceRoot"),
        data.get("workspace_root"),
        data.get("directory"),
        data.get("worktree"),
        first_string(data.get("workspace_roots")),
        first_string(data.get("workspacePaths")),
        context.get("workspaceDir"),
        context.get("cwd"),
    ]
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value
    return os.getcwd()


def hook_session_id(host: str, data: dict[str, Any]) -> str:
    context = data.get("context") if isinstance(data.get("context"), dict) else {}
    for key in ("session_id", "sessionId", "conversation_id", "conversationId", "sessionKey"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    for key in ("sessionId", "session_id", "sessionKey"):
        value = context.get(key)
        if isinstance(value, str) and value.strip():
            return value
    env = os.environ.get("PROJECT_CONTEXT_SESSION_ID")
    if env:
        return env
    return f"{host}-{uuid.uuid4()}"


def hook_source(data: dict[str, Any], default: str = "startup") -> str:
    for key in ("source", "reason", "hook_event_name", "hookEventName"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return default


def enabled_repo_from_hook(data: dict[str, Any]) -> tuple[pathlib.Path | None, dict[str, Any] | None]:
    root = discover_repo(hook_cwd(data))
    if not root:
        return None, None
    try:
        cfg = load_config(root)
    except ContextError:
        return root, None
    return root, cfg


def persist_claude_env(session_id: str, host: str) -> None:
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file:
        return
    try:
        with open(env_file, "a", encoding="utf-8") as fh:
            fh.write(f"export PROJECT_CONTEXT_SESSION_ID={json.dumps(session_id)}\n")
            fh.write(f"export PROJECT_CONTEXT_AGENT={json.dumps(host)}\n")
    except OSError:
        pass


def emit_hook_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


def session_start_output(host: str, text: str, session_id: str) -> None:
    if host in {"claude", "codex"}:
        print(text)
    elif host == "cursor":
        emit_hook_json({"env": {"PROJECT_CONTEXT_SESSION_ID": session_id, "PROJECT_CONTEXT_AGENT": host}, "additional_context": text})
    elif host == "droid":
        emit_hook_json({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}, "suppressOutput": True})
    # Grok's passive lifecycle hook stdout is not a reliable context channel.
    # OpenCode/Pi/Hermes/OpenClaw adapters inject context through their native extension APIs.


def hook_session_start(host: str, data: dict[str, Any]) -> int:
    root, cfg = enabled_repo_from_hook(data)
    if not root or not cfg:
        if host in {"cursor", "droid"}:
            emit_hook_json({})
        return 0
    session_id = hook_session_id(host, data)
    source = hook_source(data)
    state = read_json(session_state_path(root, session_id), {}) or {}
    state.update(
        {
            "session_id": session_id,
            "host": host,
            "cwd": hook_cwd(data),
            "started_at": state.get("started_at") or utc_now(),
            "last_seen_at": utc_now(),
            "source": source,
            "session_baseline_fingerprint": state.get("session_baseline_fingerprint") or git_fingerprint(root),
            "turn_baseline_fingerprint": git_fingerprint(root),
            "turn_started_at": utc_now(),
        }
    )
    write_json_atomic(session_state_path(root, session_id), state)
    write_json_atomic(active_pointer_path(root, host), {"session_id": session_id, "updated_at": utc_now()})
    if host == "claude":
        persist_claude_env(session_id, host)
    text = context_packet(root, cfg, compact=(source == "compact"))
    session_start_output(host, text, session_id)
    return 0


def hook_turn_start(host: str, data: dict[str, Any]) -> int:
    root, cfg = enabled_repo_from_hook(data)
    if not root or not cfg:
        if host == "cursor":
            emit_hook_json({"continue": True})
        elif host == "droid":
            emit_hook_json({"suppressOutput": True})
        return 0
    session_id = hook_session_id(host, data)
    state_path = session_state_path(root, session_id)
    state = read_json(state_path, {}) or {}
    now = utc_now()
    turn_id = data.get("turn_id") or data.get("generation_id") or data.get("turnId") or data.get("invocationNum")
    state.update(
        {
            "session_id": session_id,
            "host": host,
            "cwd": hook_cwd(data),
            "turn_started_at": now,
            "turn_baseline_fingerprint": git_fingerprint(root),
            "turn_id": turn_id,
            "last_seen_at": now,
        }
    )
    state.pop("skip_fingerprint", None)
    state.pop("skip_at", None)
    state.pop("skip_reason", None)
    write_json_atomic(state_path, state)
    write_json_atomic(active_pointer_path(root, host), {"session_id": session_id, "updated_at": now})
    if host == "cursor":
        emit_hook_json({"continue": True})
    elif host == "droid":
        emit_hook_json({"suppressOutput": True})
    return 0


def stop_reason(host: str, data: dict[str, Any]) -> str | None:
    root, cfg = enabled_repo_from_hook(data)
    if not root or not cfg:
        return None
    if not bool(cfg.get("hooks", {}).get("stop_check", False)):
        return None
    if data.get("stop_hook_active") or data.get("stopHookActive"):
        return None
    session_id = hook_session_id(host, data)
    state = read_json(session_state_path(root, session_id), {}) or {}
    baseline = state.get("turn_baseline_fingerprint") or state.get("session_baseline_fingerprint")
    current = git_fingerprint(root)
    if not baseline or current == baseline:
        return None
    if state.get("last_event_fingerprint") == current:
        return None
    if state.get("skip_fingerprint") == current:
        return None
    return (
        "Repository state changed during this turn after the last project-context checkpoint. "
        "Before finishing, use the project-context skill to append one rich observation/handoff describing durable changes, rationale, attempts/learnings, verification, and current state. "
        "If the change is genuinely non-durable (for example formatting-only or ephemeral), run `ctx skip --agent "
        + host
        + " --reason \"<why no durable context is needed>\"`."
    )


def stop_output(host: str, reason: str | None) -> None:
    if host in {"claude", "codex", "droid"}:
        emit_hook_json({"decision": "block", "reason": reason} if reason else {})
    elif host == "cursor":
        emit_hook_json({"followup_message": reason} if reason else {})
    elif host == "antigravity":
        emit_hook_json({"decision": "continue", "reason": reason} if reason else {"decision": "allow"})
    elif host == "hermes":
        emit_hook_json({"action": "continue", "message": reason} if reason else {})
    # Grok/OpenCode/Pi/OpenClaw integrations only audit Stop-like boundaries.


def hook_stop(host: str, data: dict[str, Any]) -> int:
    reason = stop_reason(host, data)
    stop_output(host, reason)
    return 0


def hook_pre_invocation(host: str, data: dict[str, Any]) -> int:
    """Antigravity PreInvocation: turn baseline + first-invocation memory injection."""
    if host != "antigravity":
        return hook_turn_start(host, data)
    root, cfg = enabled_repo_from_hook(data)
    if not root or not cfg:
        emit_hook_json({"injectSteps": []})
        return 0
    session_id = hook_session_id(host, data)
    state_path = session_state_path(root, session_id)
    state = read_json(state_path, {}) or {}
    invocation_num = int(data.get("invocationNum", 0) or 0)
    if invocation_num == 0:
        hook_turn_start(host, data)
    inject = []
    if not state.get("startup_injected"):
        inject.append({"ephemeralMessage": context_packet(root, cfg)})
        state = read_json(state_path, {}) or {}
        state["startup_injected"] = True
        state["last_seen_at"] = utc_now()
        write_json_atomic(state_path, state)
    emit_hook_json({"injectSteps": inject})
    return 0


def hook_compact(host: str, data: dict[str, Any], phase: str) -> int:
    root, cfg = enabled_repo_from_hook(data)
    if not root or not cfg:
        return 0
    session_id = hook_session_id(host, data)
    path = session_state_path(root, session_id)
    state = read_json(path, {}) or {}
    state.update({f"compact_{phase}_at": utc_now(), "last_seen_at": utc_now(), "host": host})
    write_json_atomic(path, state)
    return 0


def hook_session_end(host: str, data: dict[str, Any]) -> int:
    root, cfg = enabled_repo_from_hook(data)
    if not root or not cfg:
        return 0
    session_id = hook_session_id(host, data)
    path = session_state_path(root, session_id)
    state = read_json(path, {}) or {}
    state.update({"ended_at": utc_now(), "last_seen_at": utc_now(), "host": host})
    write_json_atomic(path, state)
    return 0

def repo_and_config(args: argparse.Namespace, allow_uninitialized: bool = False) -> tuple[pathlib.Path, dict[str, Any]]:
    root = discover_repo(getattr(args, "cwd", None))
    if not root:
        raise ContextError("not inside a Git repository")
    cfg = load_config(root, require_enabled=not allow_uninitialized)
    if cfg is None:
        if allow_uninitialized:
            return root, deep_merge(DEFAULT_CONFIG, {})
        raise ContextError("project-context is not enabled here; run `ctx init` first")
    return root, cfg


def cmd_init(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args, allow_uninitialized=True)
    agent_dir = root / ".agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = config_path(root)
    if cfg_path.exists() and not args.force:
        existing = read_json(cfg_path, {}) or {}
        cfg = deep_merge(DEFAULT_CONFIG, existing)
    if args.stop_check:
        cfg["hooks"]["stop_check"] = True
    write_json_atomic(cfg_path, cfg)
    lp = log_path(root, cfg)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.touch(exist_ok=True)
    schema_src = skill_root() / "assets" / "PROJECT_CONTEXT.schema.json"
    schema_dst_raw = pathlib.Path(str(cfg.get("schema_copy", ".agent/PROJECT_CONTEXT.schema.json")))
    schema_dst = schema_dst_raw if schema_dst_raw.is_absolute() else root / schema_dst_raw
    if schema_src.exists():
        shutil.copy2(schema_src, schema_dst)
    if args.instructions:
        install_repo_instructions(root)
    print(f"initialized project-context in {root}")
    print(f"config: {cfg_path.relative_to(root)}")
    print(f"log: {lp.relative_to(root) if lp.is_relative_to(root) else lp}")
    if not cfg.get("hooks", {}).get("stop_check"):
        print("stop hook enforcement: disabled (enable in .agent/project-context.json when desired)")
    return 0


def backup_original(path: pathlib.Path) -> pathlib.Path | None:
    """Keep one stable pre-project-context copy before modifying a repo instruction file."""
    if not path.exists():
        return None
    backup = path.with_name(path.name + ".project-context.bak")
    if backup.exists():
        return backup
    shutil.copy2(path, backup)
    return backup


def append_marker_block(path: pathlib.Path, block: str, marker: str) -> bool:
    begin = f"<!-- {marker}:begin -->"
    end = f"<!-- {marker}:end -->"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if begin in existing and end in existing:
        return False
    backup_original(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    separator = ""
    if existing:
        separator = "\n" if existing.endswith("\n") else "\n\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(separator + f"{begin}\n{block.strip()}\n{end}\n")
    return True


def install_repo_instructions(root: pathlib.Path) -> None:
    agents_snippet = (skill_root() / "assets" / "AGENTS.snippet.md").read_text(encoding="utf-8")
    append_marker_block(root / "AGENTS.md", agents_snippet, "project-context")
    claude = root / "CLAUDE.md"
    existing = claude.read_text(encoding="utf-8") if claude.exists() else ""
    has_import = any(line.strip() == "@AGENTS.md" for line in existing.splitlines())
    if not has_import:
        append_marker_block(claude, "@AGENTS.md", "project-context-import")


def cmd_startup(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    print(context_packet(root, cfg, scopes=args.scope, path_query=args.path, token_budget=args.budget, compact=args.compact))
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    budget = args.budget or int(cfg.get("retrieval", {}).get("token_budget", 3000))
    print(context_packet(root, cfg, scopes=args.scope, path_query=args.path, token_budget=budget, compact=False))
    return 0


def cmd_latest(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    entries = load_entries(root, cfg)[-args.count :]
    emit_entries(entries, args.format, args.full, args.budget)
    return 0


def cmd_since(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    entries = filter_entries(load_entries(root, cfg), since=args.timestamp)
    if args.latest:
        entries = entries[-args.latest :]
    emit_entries(entries, args.format, args.full, args.budget)
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    entries = filter_entries(
        load_entries(root, cfg),
        scopes=args.scope,
        path_query=args.path,
        agent=args.agent_filter,
        record_type=args.record_type,
        minimum_importance=args.minimum_importance,
    )
    if args.latest:
        entries = entries[-args.latest :]
    emit_entries(entries, args.format, args.full, args.budget)
    return 0


def extractor_header(entry: dict[str, Any]) -> str:
    agent = entry.get("agent", {}).get("name", "unknown")
    scopes = ",".join(entry.get("scope", [])) or "project"
    return f"[{entry.get('timestamp','?')}] {agent} [{scopes}] source={entry.get('entry_id','?')}"


def cmd_decisions(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    entries = filter_entries(load_entries(root, cfg), scopes=args.scope, path_query=args.path)
    blocks: list[str] = []
    for entry in entries:
        decisions = entry.get("decisions", []) or []
        if not decisions:
            continue
        lines = [extractor_header(entry)]
        for d in decisions:
            if isinstance(d, dict):
                lines.append(f"DECISION: {d.get('decision','')}")
                if d.get("rationale"):
                    lines.append(f"  rationale: {d['rationale']}")
                for alt in d.get("alternatives", []) or []:
                    if isinstance(alt, dict):
                        line = f"  alternative [{alt.get('outcome','?')}]: {alt.get('option','')}"
                        if alt.get("reason"):
                            line += f" — {alt['reason']}"
                        lines.append(line)
        blocks.append("\n".join(lines))
    print(blocks_with_budget(blocks[-args.latest :], args.budget))
    return 0


def cmd_attempts(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    entries = filter_entries(load_entries(root, cfg), scopes=args.scope, path_query=args.path)
    blocks: list[str] = []
    for entry in entries:
        selected = []
        for attempt in entry.get("attempts", []) or []:
            if not isinstance(attempt, dict):
                continue
            if args.outcome and attempt.get("outcome") != args.outcome:
                continue
            selected.append(attempt)
        if not selected:
            continue
        lines = [extractor_header(entry)]
        for a in selected:
            lines.append(f"ATTEMPT[{a.get('outcome','?')}]: {a.get('approach','')}")
            if a.get("reason"):
                lines.append(f"  reason: {a['reason']}")
            if a.get("evidence"):
                lines.append(f"  evidence: {a['evidence']}")
            if a.get("learning"):
                lines.append(f"  learning: {a['learning']}")
        blocks.append("\n".join(lines))
    print(blocks_with_budget(blocks[-args.latest :], args.budget))
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    entries = filter_entries(load_entries(root, cfg), scopes=args.scope, path_query=args.path)
    blocks: list[str] = []
    for entry in entries:
        state = entry.get("current_state")
        if not isinstance(state, dict):
            continue
        values: list[tuple[str, Any]] = [
            ("REMAINING", state.get("remaining")),
            ("BLOCKERS", state.get("blockers")),
            ("OPEN QUESTIONS", state.get("open_questions")),
            ("NEXT STEPS", state.get("next_steps")),
        ]
        if not any(v for _, v in values):
            continue
        lines = [extractor_header(entry)]
        for title, vals in values:
            lines.extend(list_strings(title, vals))
        blocks.append("\n".join(lines))
    print(blocks_with_budget(blocks[-args.latest :], args.budget))
    return 0


def cmd_blockers(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    entries = filter_entries(load_entries(root, cfg), scopes=args.scope, path_query=args.path)
    blocks: list[str] = []
    for entry in entries:
        state = entry.get("current_state")
        blockers = state.get("blockers") if isinstance(state, dict) else None
        if blockers:
            blocks.append("\n".join([extractor_header(entry), *list_strings("BLOCKERS", blockers)]))
    print(blocks_with_budget(blocks[-args.latest :], args.budget))
    return 0


def cmd_append(args: argparse.Namespace, override: str | None = None) -> int:
    root, cfg = repo_and_config(args)
    payload = read_payload(args, override)
    agent = args.agent or os.environ.get("PROJECT_CONTEXT_AGENT") or "unknown"
    entry = build_entry(root, cfg, payload, agent, args.session_id, override)
    append_entry(root, cfg, entry)
    update_runtime_after_checkpoint(root, agent, entry["agent"]["session_id"], entry["entry_id"])
    print(json.dumps({"entry_id": entry["entry_id"], "timestamp": entry["timestamp"], "record_type": entry["record_type"]}))
    return 0


def cmd_skip(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    agent = args.agent or os.environ.get("PROJECT_CONTEXT_AGENT") or "unknown"
    sid = resolve_session_id(root, agent, args.session_id)
    state_path = session_state_path(root, sid)
    state = read_json(state_path, {}) or {}
    state.update(
        {
            "session_id": sid,
            "host": state.get("host", agent),
            "skip_at": utc_now(),
            "skip_reason": args.reason,
            "skip_fingerprint": git_fingerprint(root),
        }
    )
    write_json_atomic(state_path, state)
    print(f"acknowledged non-durable turn for session {sid}: {args.reason}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    path = log_path(root, cfg)
    if not path.exists():
        print("valid: 0 entries")
        return 0
    errors: list[str] = []
    count = 0
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            count += 1
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {lineno}: invalid JSON: {exc}")
                continue
            if not isinstance(entry, dict):
                errors.append(f"line {lineno}: record is not an object")
                continue
            for error in validate_entry(entry):
                errors.append(f"line {lineno}: {error}")
    if errors:
        for error in errors:
            eprint(error)
        eprint(f"invalid: {len(errors)} errors across {count} entries")
        return 1
    print(f"valid: {count} entries")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    entries = load_entries(root, cfg)
    counts = {kind: sum(1 for e in entries if e.get("record_type") == kind) for kind in sorted(RECORD_TYPES)}
    last_ref = latest_reflection(entries)
    since_ref = 0
    if last_ref:
        idx = coverage_index(entries, last_ref)
        since_ref = sum(1 for e in entries[idx + 1 :] if e.get("record_type") in {"observation", "handoff"})
    else:
        since_ref = counts["observation"] + counts["handoff"]
    threshold = int(cfg.get("reflection", {}).get("suggest_after_observations", 20))
    data = {
        "entries": len(entries),
        "record_types": counts,
        "observations_since_reflection": since_ref,
        "reflection_suggested": since_ref >= threshold,
        "log_bytes": log_path(root, cfg).stat().st_size if log_path(root, cfg).exists() else 0,
        "latest_entry": entries[-1].get("timestamp") if entries else None,
        "latest_reflection": last_ref.get("timestamp") if last_ref else None,
    }
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    root = discover_repo(getattr(args, "cwd", None))
    print(f"project-context {PACKAGE_VERSION} / protocol {PROTOCOL_VERSION}")
    print(f"python: {sys.version.split()[0]}")
    print(f"skill root: {skill_root()}")
    host_skill_paths = {
        "codex": pathlib.Path.home() / ".agents/skills/project-context",
        "claude": pathlib.Path.home() / ".claude/skills/project-context",
        "grok": pathlib.Path.home() / ".grok/skills/project-context",
        "opencode": pathlib.Path.home() / ".config/opencode/skills/project-context",
        "cursor": pathlib.Path.home() / ".cursor/skills/project-context",
        "droid": pathlib.Path.home() / ".factory/skills/project-context",
        "pi": pathlib.Path.home() / ".pi/agent/skills/project-context",
        "antigravity": pathlib.Path.home() / ".gemini/config/skills/project-context",
        "hermes": pathlib.Path.home() / ".hermes/skills/project-context",
        "openclaw": pathlib.Path.home() / ".openclaw/skills/project-context",
    }
    for host, path in host_skill_paths.items():
        print(f"{host} skill: {path} ({'present' if path.exists() else 'missing'})")
    if not root:
        print("repo: not inside a Git repository")
        return 0
    print(f"repo: {root}")
    cfg = load_config(root, require_enabled=False)
    print(f"config: {'present' if config_path(root).exists() else 'missing'}")
    if not cfg:
        print("project-context: not initialized")
        return 0
    lp = log_path(root, cfg)
    print(f"enabled: {cfg.get('enabled', True)}")
    print(f"log: {lp} ({lp.stat().st_size if lp.exists() else 0} bytes)")
    print(f"stop_check: {cfg.get('hooks', {}).get('stop_check', False)}")
    return cmd_validate(argparse.Namespace(cwd=str(root)))


def cmd_hook(args: argparse.Namespace) -> int:
    data = parse_hook_input()
    if args.event == "session-start":
        return hook_session_start(args.host, data)
    if args.event == "turn-start":
        return hook_turn_start(args.host, data)
    if args.event == "pre-invocation":
        return hook_pre_invocation(args.host, data)
    if args.event == "compact-before":
        return hook_compact(args.host, data, "before")
    if args.event == "compact-after":
        return hook_compact(args.host, data, "after")
    if args.event == "stop":
        return hook_stop(args.host, data)
    if args.event == "session-end":
        return hook_session_end(args.host, data)
    raise ContextError(f"unknown hook event: {args.event}")


def add_common_query(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", action="append", help="scope label; repeatable")
    parser.add_argument("--path", help="repo-relative path/prefix")
    parser.add_argument("--latest", type=int, default=10)
    parser.add_argument("--budget", type=int, default=3000, help="approximate output token budget")


def add_append_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", help="semantic JSON object file, or - for stdin")
    parser.add_argument("--agent", help="agent identity, e.g. codex or claude")
    parser.add_argument("--session-id")
    parser.add_argument("--importance", choices=sorted(IMPORTANCE))
    parser.add_argument("--scope", action="append")
    parser.add_argument("--context")
    parser.add_argument("--tag", action="append")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ctx", description="Shared append-only project memory for coding agents")
    parser.add_argument("--version", action="version", version=f"project-context {PACKAGE_VERSION} protocol {PROTOCOL_VERSION}")
    parser.add_argument("--cwd", help="operate as if launched from this directory")
    subs = parser.add_subparsers(dest="command", required=True)

    p = subs.add_parser("init", help="initialize project-context in the current Git repository")
    p.add_argument("--instructions", action="store_true", help="add/update AGENTS.md bootstrap and CLAUDE.md import")
    p.add_argument("--stop-check", action="store_true", help="enable Stop hook enforcement in project config")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = subs.add_parser("startup", help="render bounded startup context")
    p.add_argument("--scope", action="append")
    p.add_argument("--path")
    p.add_argument("--budget", type=int)
    p.add_argument("--compact", action="store_true")
    p.set_defaults(func=cmd_startup)

    p = subs.add_parser("context", help="render reflection + relevant tail for a scope/path")
    p.add_argument("--scope", action="append")
    p.add_argument("--path")
    p.add_argument("--budget", type=int)
    p.set_defaults(func=cmd_context)

    p = subs.add_parser("latest", help="show latest records")
    p.add_argument("count", type=int, nargs="?", default=8)
    p.add_argument("--format", choices=["plain", "jsonl"], default="plain")
    p.add_argument("--full", action="store_true")
    p.add_argument("--budget", type=int)
    p.set_defaults(func=cmd_latest)

    p = subs.add_parser("since", help="show records after timestamp")
    p.add_argument("timestamp")
    p.add_argument("--latest", type=int)
    p.add_argument("--format", choices=["plain", "jsonl"], default="plain")
    p.add_argument("--full", action="store_true")
    p.add_argument("--budget", type=int)
    p.set_defaults(func=cmd_since)

    p = subs.add_parser("query", help="filter records")
    p.add_argument("--scope", action="append")
    p.add_argument("--path")
    p.add_argument("--agent", dest="agent_filter")
    p.add_argument("--record-type", choices=sorted(RECORD_TYPES))
    p.add_argument("--minimum-importance", choices=sorted(IMPORTANCE), default="low")
    p.add_argument("--latest", type=int, default=10)
    p.add_argument("--format", choices=["plain", "jsonl"], default="plain")
    p.add_argument("--full", action="store_true")
    p.add_argument("--budget", type=int)
    p.set_defaults(func=cmd_query)

    p = subs.add_parser("decisions", help="project decision/rationale fields")
    add_common_query(p)
    p.set_defaults(func=cmd_decisions)

    p = subs.add_parser("attempts", help="project attempts, optionally by outcome")
    add_common_query(p)
    p.add_argument("--outcome", choices=sorted(ATTEMPT_OUTCOMES))
    p.set_defaults(func=cmd_attempts)

    p = subs.add_parser("open", help="remaining work, blockers, questions, next steps")
    add_common_query(p)
    p.set_defaults(func=cmd_open)

    p = subs.add_parser("blockers", help="current blockers")
    add_common_query(p)
    p.set_defaults(func=cmd_blockers)

    p = subs.add_parser("append", help="append an observation/reflection/handoff from semantic JSON")
    add_append_args(p)
    p.set_defaults(func=lambda a: cmd_append(a, None))

    p = subs.add_parser("handoff", help="append a handoff")
    add_append_args(p)
    p.set_defaults(func=lambda a: cmd_append(a, "handoff"))

    p = subs.add_parser("reflect", help="append a reflection and auto-fill missing coverage boundaries")
    add_append_args(p)
    p.set_defaults(func=lambda a: cmd_append(a, "reflection"))

    p = subs.add_parser("skip", help="acknowledge changed Git state that has no durable project-context value")
    p.add_argument("--agent")
    p.add_argument("--session-id")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_skip)

    p = subs.add_parser("validate", help="validate all JSONL records")
    p.set_defaults(func=cmd_validate)

    p = subs.add_parser("stats", help="show log/reflection statistics")
    p.set_defaults(func=cmd_stats)

    p = subs.add_parser("doctor", help="check installation and current repository")
    p.set_defaults(func=cmd_doctor)

    p = subs.add_parser("hook", help="host lifecycle adapter")
    p.add_argument("event", choices=["session-start", "turn-start", "pre-invocation", "compact-before", "compact-after", "stop", "session-end"])
    p.add_argument("--host", choices=["claude", "codex", "grok", "opencode", "cursor", "droid", "pi", "antigravity", "hermes", "openclaw"], required=True)
    p.set_defaults(func=cmd_hook)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ContextError as exc:
        eprint(f"ctx: {exc}")
        return 2
    except KeyboardInterrupt:
        eprint("ctx: interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
