#!/usr/bin/env python3
"""project-context CLI.

Standard-library-only append/query/lifecycle utility for shared coding-agent memory.
"""
from __future__ import annotations

import argparse
import contextlib
import collections
import difflib
import errno
import math
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
import time
import uuid
from typing import Any, Iterable

PROTOCOL_VERSION = 1
PACKAGE_VERSION = "0.7.1"
RECORD_TYPES = {"observation", "reflection", "handoff"}
IMPORTANCE = {"low", "medium", "high", "critical"}
ATTEMPT_OUTCOMES = {"worked", "failed", "partial", "inconclusive", "abandoned"}
LEARNING_TYPES = {"fact", "invariant", "constraint", "convention", "gotcha", "hypothesis", "open_question"}
CONFIDENCE = {"confirmed", "likely", "tentative"}
VERIFY_OUTCOMES = {"passed", "failed", "partial", "not_run", "inconclusive"}
FILE_OPERATIONS = {"added", "modified", "deleted", "renamed", "copied", "untracked", "unknown"}
CHANGE_CAPTURE = {"agent-authored", "git-snapshot"}
CHECKPOINT_GATES = {"off", "changed-work", "every-turn"}
STORAGE_MODES = {"repo", "git-common", "external"}
TRACKING_POLICIES = {"unmanaged", "ignored", "versioned"}
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
    "checkpoint": {"stop_gate": "off"},
    "storage": {"mode": "repo", "tracking": "unmanaged"},
    "runtime": {"directory": ".agent/runtime"},
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
    if not isinstance(override, dict):
        raise ContextError("project-context configuration must be an object")
    cfg = deep_merge(DEFAULT_CONFIG, override)
    legacy_stop = bool((override.get("hooks") or {}).get("stop_check")) if isinstance(override.get("hooks"), dict) else False
    checkpoint_override = override.get("checkpoint") if isinstance(override.get("checkpoint"), dict) else {}
    if legacy_stop and "stop_gate" not in checkpoint_override:
        cfg["checkpoint"]["stop_gate"] = "changed-work"
    validate_config(root, cfg)
    if require_enabled and not cfg.get("enabled", True):
        return None
    return cfg


def log_path(root: pathlib.Path, cfg: dict[str, Any]) -> pathlib.Path:
    storage = cfg.get("storage") if isinstance(cfg.get("storage"), dict) else {}
    mode = str(storage.get("mode", "repo"))
    raw = pathlib.Path(str(storage.get("path") or cfg.get("log", DEFAULT_CONFIG["log"]))).expanduser()
    if mode == "external":
        return raw.resolve()
    if mode == "git-common":
        common = run_git(root, "rev-parse", "--git-common-dir", check=True)
        common_path = pathlib.Path(common)
        if not common_path.is_absolute():
            common_path = (root / common_path).resolve()
        relative = raw if not raw.is_absolute() else pathlib.Path(raw.name)
        if relative.as_posix() == DEFAULT_CONFIG["log"]:
            relative = pathlib.Path("project-context/PROJECT_CONTEXT.jsonl")
        return (common_path / relative).resolve()
    return raw.resolve() if raw.is_absolute() else (root / raw).resolve()


def validate_config(root: pathlib.Path, cfg: dict[str, Any]) -> None:
    for section in ("startup", "retrieval", "reflection"):
        if not isinstance(cfg.get(section), dict):
            raise ContextError(f"{section} configuration must be an object")
        for key, value in cfg[section].items():
            if key in {"token_budget", "compact_token_budget", "latest_without_reflection", "latest", "suggest_after_observations"} and (not isinstance(value, int) or isinstance(value, bool) or value <= 0):
                raise ContextError(f"{section}.{key} must be a positive integer")
    storage = cfg.get("storage")
    if not isinstance(storage, dict):
        raise ContextError("storage configuration must be an object")
    mode = storage.get("mode", "repo")
    if mode not in STORAGE_MODES:
        raise ContextError(f"storage.mode must be one of {sorted(STORAGE_MODES)}")
    tracking = storage.get("tracking", "unmanaged")
    if tracking not in TRACKING_POLICIES:
        raise ContextError(f"storage.tracking must be one of {sorted(TRACKING_POLICIES)}")
    raw = pathlib.Path(str(storage.get("path") or cfg.get("log", DEFAULT_CONFIG["log"]))).expanduser()
    if mode == "external" and not raw.is_absolute():
        raise ContextError("storage.mode external requires an absolute storage.path or log path")
    if mode == "repo":
        resolved = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ContextError("repo storage path must stay inside the repository")
    runtime = cfg.get("runtime", {})
    if not isinstance(runtime, dict) or not isinstance(runtime.get("directory", ".agent/runtime"), str):
        raise ContextError("runtime.directory must be a path string")
    checkpoint = cfg.get("checkpoint")
    if not isinstance(checkpoint, dict) or checkpoint.get("stop_gate", "off") not in CHECKPOINT_GATES:
        raise ContextError(f"checkpoint.stop_gate must be one of {sorted(CHECKPOINT_GATES)}")


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


def runtime_location(root: pathlib.Path) -> pathlib.Path:
    cfg = load_config(root, require_enabled=False) or {}
    raw = os.environ.get("PROJECT_CONTEXT_RUNTIME_DIR") or (cfg.get("runtime") or {}).get("directory", ".agent/runtime")
    base = pathlib.Path(raw).expanduser()
    if not base.is_absolute():
        base = root / base
    return (base / repo_key(root)).resolve()


def runtime_dir(root: pathlib.Path) -> pathlib.Path:
    path = runtime_location(root)
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


def linked_worktree(root: pathlib.Path) -> tuple[bool, pathlib.Path | None]:
    """Whether `root` is a linked Git worktree (its git dir is not the common dir). A repo-mode ledger there is
    separate from the main checkout's; `--storage git-common` shares one across worktrees."""
    git_dir = run_git(root, "rev-parse", "--git-dir")
    common = run_git(root, "rev-parse", "--git-common-dir")
    if not git_dir or not common:
        return False, None
    gd = pathlib.Path(git_dir)
    cd = pathlib.Path(common)
    gd = (root / gd).resolve() if not gd.is_absolute() else gd.resolve()
    cd = (root / cd).resolve() if not cd.is_absolute() else cd.resolve()
    return gd != cd, cd


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


def coordination_paths(root: pathlib.Path | None = None) -> set[str]:
    paths = {
        ".agent/PROJECT_CONTEXT.jsonl",
        ".agent/PROJECT_CONTEXT.schema.json",
        ".agent/project-context.json",
    }
    if root is None:
        return paths
    try:
        cfg = load_config(root, require_enabled=False)
    except ContextError:
        cfg = None
    if not cfg:
        return paths
    candidates = [log_path(root, cfg), log_path(root, cfg).parent / ".ctx-locks", root / ".agent" / "runtime", runtime_location(root)]
    if os.environ.get("PROJECT_CONTEXT_RUNTIME_DIR"):
        candidates.append(pathlib.Path(os.environ["PROJECT_CONTEXT_RUNTIME_DIR"]).expanduser().resolve())
    schema_raw = pathlib.Path(str(cfg.get("schema_copy", ".agent/PROJECT_CONTEXT.schema.json"))).expanduser()
    candidates.append(schema_raw.resolve() if schema_raw.is_absolute() else (root / schema_raw).resolve())
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate.is_relative_to(root.resolve()):
            paths.add(candidate.relative_to(root.resolve()).as_posix())
    return paths


def filtered_git_status(root: pathlib.Path) -> str:
    kept = []
    ignored = coordination_paths(root)
    for line in git_status_raw(root).splitlines():
        path = line[3:] if len(line) >= 4 else ""
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if any(path.replace("\\", "/") == item or path.replace("\\", "/").startswith(item + "/") for item in ignored):
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
    ignored = coordination_paths(root)
    for line in raw.splitlines():
        if len(line) < 4:
            continue
        status = line[:2]
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if any(path.replace("\\", "/") == item or path.replace("\\", "/").startswith(item + "/") for item in ignored):
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


def schema_errors(value: Any, spec: dict[str, Any], pointer: str = "") -> list[str]:
    """Validate the schema constructs shipped here, with actionable JSON Pointers."""
    errors: list[str] = []
    location = pointer or "/"
    types = {"object": dict, "array": list, "string": str, "boolean": bool, "integer": int}
    expected = spec.get("type")
    if expected in types and (not isinstance(value, types[expected]) or expected == "integer" and isinstance(value, bool)):
        return [f"{location}: type: expected {expected}"]
    if "enum" in spec and value not in spec["enum"]:
        errors.append(f"{location}: enum: got {value!r}; expected one of {spec['enum']}")
    if "const" in spec and value != spec["const"]:
        errors.append(f"{location}: const: expected {spec['const']!r}")
    if isinstance(value, str):
        if len(value.strip()) < spec.get("minLength", 0):
            errors.append(f"{location}: minLength: must be non-empty")
        if spec.get("pattern") and not re.search(spec["pattern"], value):
            errors.append(f"{location}: pattern: invalid value")
    if isinstance(value, dict):
        for key in spec.get("required", []):
            if key not in value:
                errors.append(f"{location.rstrip('/')}/{key}: required: field is missing")
        props = spec.get("properties", {})
        for key, item in value.items():
            if key in props:
                escaped = str(key).replace("~", "~0").replace("/", "~1")
                errors.extend(schema_errors(item, props[key], pointer + "/" + escaped))
        for condition in spec.get("allOf", []):
            rule = condition.get("if", {}).get("properties", {})
            if all(k in value and not schema_errors(value[k], v) for k, v in rule.items()):
                errors.extend(schema_errors(value, condition.get("then", {}), pointer))
    if isinstance(value, list):
        if spec.get("uniqueItems") and len({json.dumps(x, sort_keys=True) for x in value}) != len(value):
            errors.append(f"{location}: uniqueItems: duplicate values")
        for index, item in enumerate(value):
            errors.extend(schema_errors(item, spec.get("items", {}), pointer + f"/{index}"))
    return errors


def entry_schema() -> dict[str, Any]:
    return json.loads((skill_root() / "assets" / "PROJECT_CONTEXT.schema.json").read_text(encoding="utf-8"))


def semantic_schema(record_type: str | None = None) -> dict[str, Any]:
    schema = entry_schema()
    schema["required"] = ["record_type", "scope", "context"]
    # Reflection coverage is computed atomically by ctx; it is not author input.
    schema["allOf"] = [{"if": {"properties": {"record_type": {"const": "handoff"}}}, "then": {"required": ["current_state"]}},
                        {"if": {"properties": {"record_type": {"const": "reflection"}}}, "then": {"required": ["durable_state"]}}]
    for key in ("version", "timestamp", "entry_id", "agent", "repository"):
        schema["properties"].pop(key, None)
    return schema


def validate_semantic(payload: dict[str, Any], record_type_override: str | None = None, strict_paths: bool = True) -> list[str]:
    data = dict(payload)
    if record_type_override:
        data["record_type"] = record_type_override
    errors = schema_errors(data, semantic_schema())
    if strict_paths:
        for index, path in enumerate(payload.get("related_paths", []) if isinstance(payload.get("related_paths", []), list) else []):
            if not valid_related_path(path):
                errors.append(f"/related_paths/{index}: path: expected normalized repository-relative path")
        changes = payload.get("changes", {})
        if isinstance(changes, dict):
            for field in ("files", "artifacts"):
                for index, item in enumerate(changes.get(field, []) if isinstance(changes.get(field, []), list) else []):
                    if isinstance(item, dict) and not valid_related_path(item.get("path")):
                        errors.append(f"/changes/{field}/{index}/path: expected normalized repository-relative path")
    return errors


def valid_related_path(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip() or "\\" in value:
        return False
    path = pathlib.PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and value not in {".", "./"}


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
    errors.extend(schema_errors(entry, entry_schema()))
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
        if "dirty" in repo and not isinstance(repo.get("dirty"), bool):
            errors.append("repository.dirty must be boolean")
    if entry.get("record_type") == "reflection" and not isinstance(entry.get("coverage"), dict):
        errors.append("reflection requires coverage")
    return errors


def lock_path_for(log: pathlib.Path) -> pathlib.Path:
    # Lock identity follows the canonical ledger, never a process-specific cache.
    locks = log.resolve().parent / ".ctx-locks"
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
            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                fh.write(b"0")
                fh.flush()
            def acquire() -> None:
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl  # type: ignore
            def acquire() -> None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Windows LK_LOCK gives up after ten fixed retries, which is too short
        # for several simultaneous Git metadata captures. Use one bounded policy.
        deadline = time.monotonic() + 60
        while True:
            try:
                acquire()
                break
            except OSError as exc:
                if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                    raise
                if time.monotonic() >= deadline:
                    raise ContextError(f"timed out waiting for ledger lock: {lock_path}") from exc
                time.sleep(0.05)
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


def append_entry(root: pathlib.Path, cfg: dict[str, Any], entry: dict[str, Any], already_locked: bool = False) -> None:
    errors = validate_entry(entry)
    if errors:
        raise ContextError("invalid entry:\n- " + "\n- ".join(errors))
    path = log_path(root, cfg)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
    lock = contextlib.nullcontext() if already_locked else file_lock(path)
    with lock:
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
            "turn_checkpointed": True,
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
    sessions = [read_json(p, {}) for p in runtime_location(root).glob("session-*.json")]
    sessions = [state for state in sessions if state.get("host") == agent and not state.get("ended_at")]
    if len(sessions) == 1:
        return str(sessions[0]["session_id"])
    if len(sessions) > 1:
        eprint("ctx: multiple active sessions; use --session-id or PROJECT_CONTEXT_SESSION_ID; recording a new manual session")
    return f"manual-{uuid.uuid4()}"


def auto_changes(root: pathlib.Path, payload: dict[str, Any]) -> None:
    changes = payload.setdefault("changes", {})
    if not isinstance(changes, dict):
        return
    if changes.get("files"):
        changes.setdefault("capture", "agent-authored")
        return
    detected = detect_changed_files(root)
    if detected:
        changes["files"] = detected
        changes.setdefault("capture", "git-snapshot")


def scope_overlap(left: list[str] | None, right: list[str] | None) -> bool:
    if not left or not right:
        return True
    return bool({value.lower() for value in left}.intersection(value.lower() for value in right))


def reflection_coverage(entries: list[dict[str, Any]], payload: dict[str, Any], allow_empty: bool = False) -> None:
    coverage = payload.setdefault("coverage", {})
    if not isinstance(coverage, dict):
        payload["coverage"] = coverage = {}
    reflection_scope = [str(value) for value in payload.get("scope", []) if isinstance(value, str)]
    explicit_support = coverage.get("supporting_entry_ids")
    if "supporting_entry_ids" in coverage:
        if not explicit_support and not allow_empty:
            raise ContextError("reflection has empty explicit coverage; select sources or use --allow-empty-coverage")
        known = {str(entry.get("entry_id")) for entry in entries}
        missing = [entry_id for entry_id in explicit_support if entry_id not in known]
        if missing:
            raise ContextError("reflection coverage references unknown entries: " + ", ".join(missing))
        coverage.setdefault("scope", reflection_scope)
        return
    covered = covered_entry_ids(entries, reflection_scope or None)
    candidates = [entry for entry in entries
                  if entry.get("record_type") in {"observation", "handoff"}
                  and scope_overlap(reflection_scope, entry.get("scope", []))
                  and entry.get("entry_id") not in covered]
    if not candidates:
        if not allow_empty:
            raise ContextError("reflection has no unreflected observations or handoffs in its scope; use --allow-empty-coverage to record an explicit baseline")
        coverage.setdefault("supporting_entry_ids", [])
        coverage.setdefault("scope", reflection_scope)
        return
    coverage.setdefault("from_entry_id", candidates[0].get("entry_id"))
    coverage.setdefault("through_entry_id", candidates[-1].get("entry_id"))
    coverage.setdefault("supporting_entry_ids", [entry["entry_id"] for entry in candidates if entry.get("entry_id")])
    coverage.setdefault("scope", reflection_scope)
    if not payload.get("related_paths"):
        inherited = sorted({path for entry in candidates for path in entry_paths(entry)})
        if inherited:
            payload["related_paths"] = inherited


def build_entry(
    root: pathlib.Path,
    cfg: dict[str, Any],
    payload: dict[str, Any],
    agent: str,
    session_id: str | None,
    record_type_override: str | None = None,
    entries: list[dict[str, Any]] | None = None,
    allow_empty_coverage: bool = False,
) -> dict[str, Any]:
    payload = json.loads(json.dumps(payload))
    if record_type_override:
        payload["record_type"] = record_type_override
    payload.setdefault("importance", "medium")
    errors = validate_semantic(payload, record_type_override)
    for key in payload:
        if key not in entry_schema()["properties"] and key not in {"idempotency_key", "idempotency_digest"}:
            nearest = difflib.get_close_matches(key, entry_schema()["properties"], n=1, cutoff=0.80)
            if nearest:
                eprint(f"ctx: unknown field /{key}; did you mean /{nearest[0]}?")
    if errors:
        raise ContextError("invalid semantic payload:\n- " + "\n- ".join(errors))
    if payload.get("record_type") == "reflection":
        reflection_coverage(entries if entries is not None else load_entries(root, cfg), payload, allow_empty_coverage)
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
    if not entry_scopes or "project" in entry_scopes:
        return True
    return bool(entry_scopes.intersection({x.lower() for x in scopes}))


def entry_paths(
    entry: dict[str, Any],
    entries_by_id: dict[str, dict[str, Any]] | None = None,
    seen: set[str] | None = None,
) -> list[str]:
    paths: list[str] = [str(path) for path in entry.get("related_paths", []) or [] if isinstance(path, str)]
    changes = entry.get("changes", {})
    if isinstance(changes, dict):
        for file in changes.get("files", []) or []:
            if isinstance(file, dict) and isinstance(file.get("path"), str):
                paths.append(file["path"])
        for artifact in changes.get("artifacts", []) or []:
            if isinstance(artifact, dict) and isinstance(artifact.get("path"), str):
                paths.append(artifact["path"])
    coverage = entry.get("coverage")
    if entries_by_id and isinstance(coverage, dict):
        visited = seen or set()
        for entry_id in coverage.get("supporting_entry_ids", []) or []:
            if not isinstance(entry_id, str) or entry_id in visited:
                continue
            source = entries_by_id.get(entry_id)
            if source:
                visited.add(entry_id)
                paths.extend(entry_paths(source, entries_by_id, visited))
    return sorted(set(paths))


def matches_path(
    entry: dict[str, Any],
    path_query: str | None,
    entries_by_id: dict[str, dict[str, Any]] | None = None,
) -> bool:
    if not path_query:
        return True
    if isinstance(path_query, list):
        return any(matches_path(entry, item, entries_by_id) for item in path_query)
    q = path_query.replace("\\", "/").lower().rstrip("/")
    for path in entry_paths(entry, entries_by_id):
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
    reference_entries: Iterable[dict[str, Any]] | None = None,
    session: str | None = None,
    task: str | None = None,
) -> list[dict[str, Any]]:
    entries = list(entries)
    references = list(reference_entries) if reference_entries is not None else entries
    entries_by_id = {str(entry.get("entry_id")): entry for entry in references if entry.get("entry_id")}
    since_dt = parse_timestamp(since) if since else None
    min_weight = IMPORTANCE_WEIGHT.get(minimum_importance or "low", 0)
    out: list[dict[str, Any]] = []
    for entry in entries:
        if not matches_scope(entry, scopes) or not matches_path(entry, path_query, entries_by_id):
            continue
        if agent and str(entry.get("agent", {}).get("name", "")).lower() != agent.lower():
            continue
        if record_type and entry.get("record_type") != record_type:
            continue
        if session and str(entry.get("agent", {}).get("session_id", "")) != session:
            continue
        if task and str((entry.get("task") or {}).get("id", "") if isinstance(entry.get("task"), dict) else "") != task:
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
    lines = [header]
    if entry.get("state_resolution"):
        lines.append("STATE RESOLVED: " + entry["state_resolution"])
    lines.append(str(entry.get("context", "")).strip())

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
    for block in reversed(blocks):
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


def covered_entry_ids(entries: list[dict[str, Any]], scopes: list[str] | None = None) -> set[str]:
    """Only explicit source coverage can suppress a fact, and only in its scope."""
    by_id = {e.get("entry_id"): e for e in entries}
    covered: set[str] = set()
    for reflection in entries:
        if reflection.get("record_type") != "reflection":
            continue
        coverage = reflection.get("coverage") or {}
        if not isinstance(coverage, dict):
            continue
        declared = coverage.get("scope", reflection.get("scope", []))
        ref_scopes = {s.lower() for s in declared}
        for source_id in coverage.get("supporting_entry_ids", []) or []:
            source = by_id.get(source_id)
            if not source:
                continue
            source_scopes = {s.lower() for s in source.get("scope", [])}
            needed = source_scopes.intersection(s.lower() for s in scopes) if scopes else source_scopes
            if not ref_scopes or "project" in ref_scopes or (needed and needed <= ref_scopes):
                covered.add(source_id)
    return covered


def active_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply explicit resolution only; shared scopes never imply completion."""
    removed: set[str] = set()
    resolved: dict[str, list[str]] = collections.defaultdict(list)
    # Relations authored by superseded records are retained as historical actions.
    for entry in entries:
        relations = entry.get("related_entries") or {}
        removed.update(relations.get("supersedes", []))
        for reference in relations.get("resolves", []):
            source, _, pointer = reference.partition("#")
            resolved[source].append(pointer)
    out = []
    for entry in entries:
        eid = entry.get("entry_id")
        if eid in removed:
            continue
        item = json.loads(json.dumps(entry))
        pointers = resolved.get(eid, [])
        if "" in pointers:
            item.pop("current_state", None)
            item["state_resolution"] = "resolved by a later source; use history for the original frontier"
        else:
            # Delete array members descending so sibling indexes stay stable.
            for pointer in sorted(set(pointers), key=lambda x: (x.rsplit("/", 1)[0], int(x.rsplit("/", 1)[-1]) if x.rsplit("/", 1)[-1].isdigit() else -1), reverse=True):
                parts = pointer.lstrip("/").split("/")
                target: Any = item
                try:
                    for part in parts[:-1]:
                        target = target[int(part)] if isinstance(target, list) else target[part]
                    if isinstance(target, list):
                        target.pop(int(parts[-1]))
                    else:
                        target.pop(parts[-1], None)
                except (KeyError, IndexError, TypeError, ValueError):
                    pass
        out.append(item)
    return out


def validate_relations(payload: dict[str, Any], entries: list[dict[str, Any]]) -> None:
    by_id = {e.get("entry_id"): e for e in entries}
    for kind, refs in (payload.get("related_entries") or {}).items():
        if kind not in {"resolves", "supersedes", "related"}:
            continue
        for reference in refs:
            source, _, pointer = reference.partition("#")
            if source not in by_id:
                raise ContextError(f"/related_entries/{kind}: unknown source {source}")
            if pointer:
                if kind != "resolves" or not pointer.startswith("/current_state/"):
                    raise ContextError("resolution pointers must address /current_state fields or items")
                target: Any = by_id[source]
                try:
                    for part in pointer.lstrip("/").split("/"):
                        target = target[int(part)] if isinstance(target, list) else target[part]
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    raise ContextError(f"invalid resolution pointer: {reference}") from exc


def select_context_entries(
    entries: list[dict[str, Any]],
    scopes: list[str] | None,
    path_query: str | None,
    latest_without_reflection: int,
    session: str | None = None,
    task: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    relevant = filter_entries(entries, scopes=scopes, path_query=path_query, session=session, task=task)
    reflections = [e for e in relevant if e.get("record_type") == "reflection"]
    reflection = reflections[-1] if reflections else None
    covered = covered_entry_ids(relevant, scopes)
    tail = [e for e in relevant if e.get("entry_id") not in covered and e is not reflection]
    high = [e for e in tail if IMPORTANCE_WEIGHT.get(str(e.get("importance", "low")), 0) >= IMPORTANCE_WEIGHT["high"]]
    handoffs = [e for e in tail if e.get("record_type") == "handoff"]
    selected = {str(e.get("entry_id")): e for e in [*reflections[:-1], *high, *handoffs, *tail[-latest_without_reflection:]]}
    return sorted(selected.values(), key=entry_timestamp), reflection


def prioritized_frontier(entries: list[dict[str, Any]]) -> list[tuple[dict[str, Any], str]]:
    ordered: list[tuple[dict[str, Any], str]] = []
    handoffs = [entry for entry in entries if entry.get("record_type") == "handoff"]
    if handoffs:
        ordered.append((handoffs[-1], "latest-handoff"))
    if entries:
        ordered.append((entries[-1], "newest-frontier"))
    for entry in reversed(entries):
        if IMPORTANCE_WEIGHT.get(str(entry.get("importance", "low")), 0) >= IMPORTANCE_WEIGHT["high"]:
            ordered.append((entry, "high-importance"))
    for entry in reversed(entries):
        ordered.append((entry, "recent-frontier"))
    result: list[tuple[dict[str, Any], str]] = []
    seen: set[str] = set()
    for entry, reason in ordered:
        entry_id = str(entry.get("entry_id", id(entry)))
        if entry_id not in seen:
            result.append((entry, reason))
            seen.add(entry_id)
    return result


def brief_entry(entry: dict[str, Any], max_chars: int) -> str:
    header = f"{entry.get('record_type','?')} [{','.join(entry.get('scope', []))}] source={entry.get('entry_id','?')}"
    state = entry.get("current_state") or {}
    durable = entry.get("durable_state") or {}
    cards: list[str] = []
    if entry.get("state_resolution"):
        cards.append("STATE RESOLVED: " + entry["state_resolution"])
    if state.get("status"):
        cards.append(f"STATE: {state['status']}")
    for key in ("blockers", "next_steps", "remaining", "open_questions", "working"):
        cards.extend(f"{key.upper()}: {v}" for v in state.get(key, []) or [])
    for key in ("constraints", "open_work", "architecture", "decisions", "known_failed_approaches", "successful_approaches", "completed"):
        cards.extend(f"DURABLE {key.upper()}: {v}" for v in durable.get(key, []) or [])
    cards.extend(f"VERIFY[{v.get('outcome')}]: {v.get('check')} {v.get('details','')}" for v in entry.get("verification", []) or [])
    cards.extend(f"DECISION: {v.get('decision')} — {v.get('rationale')}" for v in entry.get("decisions", []) or [])
    cards.extend(f"LEARNING[{v.get('type')}]: {v.get('statement')}" for v in entry.get("learnings", []) or [])
    cards.append(str(entry.get("context", "")))
    suffix = f"\nEXPAND: ctx show {entry.get('entry_id')}"
    available = max(0, max_chars - len(header) - len(suffix) - 2)
    if not available:
        return trim_text(header, max_chars)
    # Bound each field independently so the first large field cannot eat all others.
    lines = [header]
    per_field = max(80, available // min(max(len(cards), 1), 5))
    for card in cards:
        remaining = available - sum(len(x) + 1 for x in lines[1:])
        if remaining <= 20:
            break
        lines.append(trim_text(card, min(remaining, per_field)))
    return trim_text("\n".join(lines) + suffix, max_chars)


def pack_context_packet(
    header: str,
    reflection: dict[str, Any] | None,
    frontier: list[dict[str, Any]],
    token_budget: int,
    help_text: str | None,
    explain: bool,
) -> str:
    maximum = approx_char_budget(token_budget)
    blocks = [header]
    used = len(header)
    selected: list[tuple[dict[str, Any], str, str]] = []
    omitted = 0
    if reflection:
        raw = "DURABLE REFLECTION\n" + format_entry(reflection, full=False)
        cap = max(400, int(maximum * 0.40))
        block = "DURABLE REFLECTION\n" + brief_entry(reflection, min(cap, max(200, maximum - used)) - 20)
        blocks.append(block)
        used += len(block) + 2
    reserve = len(help_text or "") + (2 if help_text else 0)
    for entry, reason in prioritized_frontier(frontier):
        raw = format_entry(entry, full=False)
        remaining = maximum - used - reserve - 32
        if remaining <= 200:
            omitted += 1
            continue
        # Preserve the latest handoff/newest record even when individually verbose.
        if len(raw) > remaining:
            if reason in {"latest-handoff", "newest-frontier"}:
                raw = brief_entry(entry, min(remaining, max(400, int(maximum * 0.40))))
            else:
                omitted += 1
                continue
        selected.append((entry, reason, raw))
        used += len(raw) + 2
    if selected:
        selected.sort(key=lambda item: entry_timestamp(item[0]))
        blocks.append("RECENT / UNREFLECTED FRONTIER\n" + "\n\n".join(rendered for _, _, rendered in selected))
    if explain:
        lines = ["SELECTION EXPLANATION"]
        if reflection:
            lines.append(f"- {reflection.get('entry_id')}: relevant-reflection")
        lines.extend(f"- {entry.get('entry_id')}: {reason}" + ("; fields summarized, expand with ctx show" if "EXPAND: ctx show" in rendered else "") for entry, reason, rendered in selected)
        lines.append(f"- omitted_by_budget: {omitted}")
        blocks.append("\n".join(lines))
    if help_text:
        blocks.append(help_text)
    return trim_text("\n\n".join(blocks), maximum)


def scope_inventory(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for entry in entries:
        for scope in entry.get("scope", []) or ["project"]:
            row = inventory.setdefault(scope, {"scope": scope, "count": 0, "paths": []})
            row["count"] += 1
            row["latest"] = entry.get("timestamp")
            row["paths"] = list(dict.fromkeys([*entry_paths(entry), *row["paths"]]))[:3]
    return sorted(inventory.values(), key=lambda row: (-row["count"], row["scope"]))


def tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]+", text.casefold(), re.UNICODE)


def ranked_entries(entries: list[dict[str, Any]], query: str) -> list[tuple[float, dict[str, Any], str]]:
    """Local field-weighted BM25. No network, model, or persistent index required."""
    terms = list(dict.fromkeys(tokens(query)))
    if not terms:
        return []
    fields: list[tuple[dict[str, Any], str, float, list[str]]] = []
    for entry in entries:
        values = [(entry.get("context", ""), 1.0), (" ".join(entry_paths(entry)), 2.5), (" ".join(entry.get("scope", [])), 1.5)]
        for name, weight in (("decisions", 1.6), ("learnings", 1.6), ("current_state", 2.0), ("durable_state", 2.0), ("attempts", 1.2)):
            if entry.get(name):
                values.append((json.dumps(entry[name], ensure_ascii=False), weight))
        for value, weight in values:
            words = tokens(str(value))
            if words:
                fields.append((entry, str(value), weight, words))
    if not fields:
        return []
    avg_len = sum(len(words) for _, _, _, words in fields) / len(fields)
    frequency = collections.Counter(word for _, _, _, words in fields for word in set(words))
    scores: dict[str, tuple[float, dict[str, Any], str]] = {}
    for entry, value, weight, words in fields:
        counts = collections.Counter(words)
        score = 0.0
        for term in terms:
            tf = counts[term]
            if tf:
                idf = math.log(1 + (len(fields) - frequency[term] + 0.5) / (frequency[term] + 0.5))
                score += weight * idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * len(words) / avg_len))
        if not score:
            continue
        eid = str(entry.get("entry_id"))
        prior = scores.get(eid)
        snippet = value
        pos = min((value.casefold().find(term) for term in terms if term in value.casefold()), default=0)
        snippet = value[max(0, pos - 70):max(0, pos - 70) + 260].replace("\n", " ")
        scores[eid] = (score + (prior[0] if prior else 0), entry, snippet if not prior or score > prior[0] else prior[2])
    return sorted(scores.values(), key=lambda row: (row[0], entry_timestamp(row[1])), reverse=True)


def no_match_message(entries: list[dict[str, Any]], scopes: list[str] | None = None) -> str:
    names = [row["scope"] for row in scope_inventory(entries)]
    suggestions = list(dict.fromkeys(name for scope in scopes or [] for name in difflib.get_close_matches(scope, names, n=3, cutoff=0.25)))
    return ("No matching memory. Filters were not broadened.\n" +
            ("Related scopes: " + ", ".join(suggestions) + "\n" if suggestions else "") +
            "Discover: ctx scopes | Retry: ctx search \"describe the task\"")


def search_packet(entries: list[dict[str, Any]], query: str, budget: int, limit: int = 6, scopes: list[str] | None = None) -> str:
    hits = ranked_entries(entries, query)
    if not hits:
        return no_match_message(entries, scopes)
    maximum = approx_char_budget(budget)
    blocks = [f"SEARCH {query!r} matched={len(hits)}"]
    for score, entry, snippet in hits[:limit]:
        remaining = maximum - sum(len(x) + 2 for x in blocks)
        if remaining < 200:
            break
        blocks.append(f"score={score:.2f} snippet={snippet}\n" + brief_entry(entry, min(remaining - 60 - len(snippet), max(240, maximum // max(1, min(limit, len(hits)))))))
    return trim_text("\n\n".join(blocks), maximum)


def context_packet(
    root: pathlib.Path,
    cfg: dict[str, Any],
    scopes: list[str] | None = None,
    path_query: str | None = None,
    token_budget: int | None = None,
    compact: bool = False,
    explain: bool = False,
    session: str | None = None,
    task: str | None = None,
    query: str | None = None,
    history: bool = False,
) -> str:
    raw_entries = load_entries(root, cfg)
    entries = raw_entries if history else active_entries(raw_entries)
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
    relevant = filter_entries(entries, scopes=scopes, path_query=path_query, session=session, task=task)
    if not relevant:
        return no_match_message(entries, scopes)
    if query:
        return search_packet(relevant, query, token_budget, scopes=scopes)
    selected, reflection = select_context_entries(entries, scopes, path_query, default_latest, session, task)
    scope_label = ",".join(scopes or []) or (",".join(path_query) if isinstance(path_query, list) else path_query or "project")
    if session:
        scope_label += f" session={session}"
    if task:
        scope_label += f" task={task}"
    header = [
        f"PROJECT MEMORY — {scope_label}",
        f"repository: {root.name}",
        f"entries: {len(raw_entries)} matched={len(relevant)} selected={len(selected) + int(reflection is not None)}",
    ]
    help_text = None
    if not compact:
        help_text = (
            "USE TARGETED RETRIEVAL IF NEEDED\n"
            "ctx context --scope <scope> | ctx context --path <path> | ctx attempts --outcome failed | ctx decisions | ctx open"
        )
    return pack_context_packet("\n".join(header), reflection, selected, token_budget, help_text, explain)


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


def startup_delivery(root: pathlib.Path, cfg: dict[str, Any], host: str, session_id: str, compact: bool = False, budget: int | None = None) -> str:
    text = context_packet(root, cfg, token_budget=budget, compact=compact)
    digest = hashlib.sha256(text.encode()).hexdigest()
    path = session_state_path(root, session_id)
    state = read_json(path, {}) or {}
    if not compact and state.get("packet_hash") == digest and state.get("last_emitted_at") and not state.get("refresh_pending"):
        return ""
    # Persist emission metadata only; receiving-harness consumption is unobservable.
    state.update({"session_id": session_id, "host": host, "packet_hash": digest,
                  "last_emitted_at": utc_now(), "packet_estimated_tokens": (len(text) + 3) // 4,
                  "refresh_pending": False, "delivery_status": "emitted_not_acknowledged"})
    write_json_atomic(path, state)
    return text


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
    gate = str((cfg.get("checkpoint") or {}).get("stop_gate", "off"))
    fingerprint = git_fingerprint(root) if gate != "off" else None
    state.update(
        {
            "session_id": session_id,
            "host": host,
            "cwd": hook_cwd(data),
            "started_at": state.get("started_at") or utc_now(),
            "last_seen_at": utc_now(),
            "source": source,
            "turn_started_at": utc_now(),
        }
    )
    if fingerprint:
        state["session_baseline_fingerprint"] = state.get("session_baseline_fingerprint") or fingerprint
        state["turn_baseline_fingerprint"] = fingerprint
    write_json_atomic(session_state_path(root, session_id), state)
    write_json_atomic(active_pointer_path(root, host), {"session_id": session_id, "updated_at": utc_now()})
    if host == "claude":
        persist_claude_env(session_id, host)
    text = startup_delivery(root, cfg, host, session_id, compact=(source == "compact")) if host in {"claude", "codex", "cursor", "droid"} else ""
    session_start_output(host, text, session_id)
    return 0


def hook_turn_start(host: str, data: dict[str, Any]) -> int:
    root, cfg = enabled_repo_from_hook(data)
    if not root or not cfg:
        turn_start_output(host)
        return 0
    if str((cfg.get("checkpoint") or {}).get("stop_gate", "off")) == "off":
        # With no Stop gate there is nothing to compare at turn end. Avoid the
        # Git status scan and runtime-state writes on every prompt.
        turn_start_output(host)
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
            "turn_checkpointed": False,
            "last_seen_at": now,
        }
    )
    state.pop("skip_fingerprint", None)
    state.pop("skip_at", None)
    state.pop("skip_reason", None)
    write_json_atomic(state_path, state)
    write_json_atomic(active_pointer_path(root, host), {"session_id": session_id, "updated_at": now})
    turn_start_output(host)
    return 0


def turn_start_output(host: str) -> None:
    if host == "cursor":
        emit_hook_json({"continue": True})
    elif host == "droid":
        emit_hook_json({"suppressOutput": True})


def checkpoint_due(root: pathlib.Path, cfg: dict[str, Any], host: str, data: dict[str, Any]) -> tuple[bool, str]:
    gate = str((cfg.get("checkpoint") or {}).get("stop_gate", "off"))
    if gate == "off":
        return False, "checkpoint stop gate is off"
    session_id = hook_session_id(host, data)
    state = read_json(session_state_path(root, session_id), {}) or {}
    if state.get("turn_checkpointed"):
        return False, "current turn was checkpointed or explicitly skipped"
    if gate == "every-turn":
        return True, "every completed turn requires an observation, handoff, reflection, or explicit skip"
    baseline = state.get("turn_baseline_fingerprint") or state.get("session_baseline_fingerprint")
    current = git_fingerprint(root)
    if not baseline:
        return False, "no session or turn baseline is available"
    if current == baseline:
        return False, "Git state is unchanged"
    if state.get("last_event_fingerprint") == current:
        return False, "current Git state was already checkpointed"
    if state.get("skip_fingerprint") == current:
        return False, "current Git state was explicitly skipped"
    return True, "Git state changed after the last checkpoint"


def stop_reason(host: str, data: dict[str, Any]) -> str | None:
    root, cfg = enabled_repo_from_hook(data)
    if not root or not cfg:
        return None
    if data.get("stop_hook_active") or data.get("stopHookActive"):
        return None
    if str(data.get("status", "")).lower() in {"aborted", "error"}:
        return None
    if data.get("fullyIdle") is False:
        return None
    due, _ = checkpoint_due(root, cfg, host, data)
    if not due:
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
    state.update({f"compact_{phase}_at": utc_now(), "last_seen_at": utc_now(), "host": host, "refresh_pending": True})
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
        cfg["checkpoint"]["stop_gate"] = "changed-work"
    if args.checkpoint_gate:
        cfg["checkpoint"]["stop_gate"] = args.checkpoint_gate
    if args.storage:
        cfg["storage"]["mode"] = args.storage
    if args.storage_path:
        cfg["storage"]["path"] = args.storage_path
    if args.tracking:
        cfg["storage"]["tracking"] = args.tracking
    validate_config(root, cfg)
    write_json_atomic(cfg_path, cfg)
    lp = log_path(root, cfg)
    lp.parent.mkdir(parents=True, exist_ok=True)
    lp.touch(exist_ok=True)
    schema_src = skill_root() / "assets" / "PROJECT_CONTEXT.schema.json"
    schema_dst_raw = pathlib.Path(str(cfg.get("schema_copy", ".agent/PROJECT_CONTEXT.schema.json")))
    schema_dst = schema_dst_raw if schema_dst_raw.is_absolute() else root / schema_dst_raw
    if schema_src.exists():
        schema_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(schema_src, schema_dst)
    if args.instructions:
        install_repo_instructions(root)
    if cfg.get("storage", {}).get("tracking") == "ignored" and cfg.get("storage", {}).get("mode") == "repo":
        raw_log = pathlib.Path(str(cfg.get("storage", {}).get("path") or cfg.get("log", DEFAULT_CONFIG["log"])))
        append_marker_block(root / ".gitignore", "/" + raw_log.as_posix().lstrip("/"), "project-context-storage")
    print(f"initialized project-context in {root}")
    linked, common = linked_worktree(root)
    if linked and cfg.get("storage", {}).get("mode", "repo") == "repo":
        print(f"warning: {root} is a linked worktree; a repo-mode ledger here is separate from the main checkout's "
              f"(common Git dir: {common}). To share one ledger across worktrees: ctx init --storage git-common --force")
    print(f"config: {cfg_path.relative_to(root)}")
    print(f"log: {lp.relative_to(root) if lp.is_relative_to(root) else lp}")
    print(f"storage: {cfg.get('storage', {}).get('mode', 'repo')} / {cfg.get('storage', {}).get('tracking', 'unmanaged')}")
    print(f"checkpoint stop gate: {cfg.get('checkpoint', {}).get('stop_gate', 'off')}")
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


def cmd_search(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    entries = load_entries(root, cfg)
    if not args.history:
        entries = active_entries(entries)
    entries = filter_entries(entries, scopes=args.scope, path_query=args.path)
    print(search_packet(entries, args.query, args.budget, args.latest, args.scope))
    return 0


def cmd_scopes(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    rows = scope_inventory(active_entries(load_entries(root, cfg)))
    if args.json:
        print(json.dumps(rows, ensure_ascii=False))
    else:
        for row in rows:
            print(f"{row['scope']} count={row['count']} paths={','.join(row['paths'])}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    entries = load_entries(root, cfg)
    matches = [e for e in entries if str(e.get("entry_id", "")).startswith(args.entry_id)]
    if len(matches) != 1:
        raise ContextError("entry ID must match exactly one record; use ctx search or ctx scopes")
    entry = matches[0]
    if args.section:
        if args.section not in entry:
            raise ContextError(f"section {args.section!r} absent; available: {', '.join(entry)}")
        print(trim_text(json.dumps(entry[args.section], ensure_ascii=False, indent=2), approx_char_budget(args.budget)))
    elif args.json:
        print(json.dumps(entry, ensure_ascii=False))
    else:
        print(trim_text(format_entry(entry, full=True), approx_char_budget(args.budget)))
    return 0


def template_payload(kind: str) -> dict[str, Any]:
    payload: dict[str, Any] = {"record_type": kind, "scope": ["subsystem"], "context": "Explain the durable result and why it matters."}
    if kind == "handoff":
        payload["current_state"] = {"status": "in_progress", "next_steps": ["Concrete next action."]}
    elif kind == "reflection":
        payload["durable_state"] = {"constraints": ["Verified constraint."], "open_work": []}
    else:
        payload["verification"] = [{"check": "What was checked", "outcome": "passed", "details": "Exact result and limitations."}]
    return payload


def cmd_template(args: argparse.Namespace) -> int:
    payload = template_payload(args.record_type)
    if not args.minimal:
        payload["importance"] = "medium"
        payload["related_paths"] = []
        payload["decisions"] = []
        payload["attempts"] = []
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    schema = semantic_schema() if not args.stored else entry_schema()
    if args.section:
        if args.section not in schema["properties"]:
            raise ContextError("unknown schema section: " + args.section)
        schema = schema["properties"][args.section]
    print(json.dumps(schema, ensure_ascii=False, indent=2))
    return 0


def cmd_reflect(args: argparse.Namespace) -> int:
    if not args.prepare:
        return cmd_append(args, "reflection")
    root, cfg = repo_and_config(args)
    entries = active_entries(load_entries(root, cfg))
    relevant = filter_entries(entries, scopes=args.scope)
    covered = covered_entry_ids(entries, args.scope)
    sources = [e for e in relevant if e.get("record_type") in {"observation", "handoff"} and e.get("entry_id") not in covered]
    previous = [e for e in relevant if e.get("record_type") == "reflection"]
    maximum = approx_char_budget(args.budget)
    selected: list[dict[str, Any]] = []
    used = 650
    for entry in sources[args.offset:args.offset + args.latest]:
        if used + 850 > maximum:
            break
        selected.append(entry)
        used += 850
    header = f"REFLECTION PREPARATION uncovered={len(sources)} shown={len(selected)} offset={args.offset}\nReview sources with ctx show before claiming coverage."
    prepared = template_payload("reflection")
    prepared["scope"] = args.scope or []
    prepared["coverage"] = {"scope": args.scope or [], "supporting_entry_ids": [e["entry_id"] for e in selected]}
    blocks = [header, "TEMPLATE: " + json.dumps(prepared)]
    if previous:
        blocks.append("PREVIOUS REFLECTION: " + brief_entry(previous[-1], 500))
    blocks.extend(brief_entry(e, 650) for e in selected)
    if args.offset + len(selected) < len(sources):
        scope_flags = " ".join("--scope " + scope for scope in args.scope or [])
        blocks.append(f"MORE: ctx reflect --prepare {scope_flags} --offset {args.offset + len(selected)} --budget {max(args.budget, 500)}")
    print(trim_text("\n\n".join(blocks), maximum))
    return 0


def cmd_startup(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    if args.delivery:
        if not args.session_id:
            raise ContextError("startup --delivery requires --session-id")
        print(startup_delivery(root, cfg, args.agent or "unknown", args.session_id, compact=args.compact, budget=args.budget))
    else:
        print(context_packet(root, cfg, scopes=args.scope, path_query=args.path, token_budget=args.budget, compact=args.compact))
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    budget = args.budget or int(cfg.get("retrieval", {}).get("token_budget", 3000))
    print(context_packet(root, cfg, scopes=args.scope, path_query=args.path, token_budget=budget, compact=False, explain=args.explain,
                         session=args.session, task=args.task, query=args.query, history=args.history))
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
        session=args.session,
        task=args.task,
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
    entries = filter_entries(load_entries(root, cfg) if getattr(args, "history", False) else active_entries(load_entries(root, cfg)), scopes=args.scope, path_query=args.path)
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


def attempt_key(attempt: dict[str, Any]) -> tuple[str, str]:
    return (" ".join(str(attempt.get("approach", "")).casefold().split()), str(attempt.get("outcome", "")))


def cmd_attempts(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    entries = filter_entries(load_entries(root, cfg) if getattr(args, "history", False) else active_entries(load_entries(root, cfg)), scopes=args.scope, path_query=args.path)
    group = not getattr(args, "no_group", False)
    # Fold repeats: the same approach with the same outcome, recorded by several sessions or tools, is one fact with a count.
    occurrences: dict[tuple[str, str], list[str]] = {}
    if group:
        for entry in entries:
            for attempt in entry.get("attempts", []) or []:
                if isinstance(attempt, dict) and (not args.outcome or attempt.get("outcome") == args.outcome):
                    occurrences.setdefault(attempt_key(attempt), []).append(str(entry.get("entry_id", "?")))
    shown: set[tuple[str, str]] = set()
    blocks: list[str] = []
    for entry in entries:
        selected = []
        for attempt in entry.get("attempts", []) or []:
            if not isinstance(attempt, dict):
                continue
            if args.outcome and attempt.get("outcome") != args.outcome:
                continue
            if group:
                key = attempt_key(attempt)
                if key in shown:
                    continue
                shown.add(key)
            selected.append(attempt)
        if not selected:
            continue
        lines = [extractor_header(entry)]
        for a in selected:
            others = [i for i in occurrences.get(attempt_key(a), []) if i != str(entry.get("entry_id", "?"))] if group else []
            lines.append(f"ATTEMPT[{a.get('outcome','?')}]" + (f" ×{len(others) + 1}" if others else "") + f": {a.get('approach','')}")
            if others:
                lines.append(f"  also in: {', '.join(others)}")
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
    entries = filter_entries(load_entries(root, cfg) if getattr(args, "history", False) else active_entries(load_entries(root, cfg)), scopes=args.scope, path_query=args.path)
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
    entries = filter_entries(load_entries(root, cfg) if getattr(args, "history", False) else active_entries(load_entries(root, cfg)), scopes=args.scope, path_query=args.path)
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
    errors = validate_semantic(payload, override)
    if errors:
        raise ContextError("invalid semantic payload:\n- " + "\n- ".join(errors))
    key = getattr(args, "idempotency_key", None) or payload.get("idempotency_key")
    if key:
        payload["idempotency_key"] = key
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if key:
        payload["idempotency_digest"] = digest
    agent = args.agent or os.environ.get("PROJECT_CONTEXT_AGENT") or "unknown"
    path = log_path(root, cfg)
    if getattr(args, "check", False):
        if key:
            prior = next((e for e in load_entries(root, cfg) if e.get("idempotency_key") == key), None)
            if prior and prior.get("idempotency_digest") != digest:
                raise ContextError("idempotency key already used for a different semantic payload")
        entry = build_entry(root, cfg, payload, agent, args.session_id or "check-only", override, entries=load_entries(root, cfg),
                            allow_empty_coverage=bool(getattr(args, "allow_empty_coverage", False)))
        validate_relations(payload, load_entries(root, cfg))
        errors = validate_entry(entry)
        if errors:
            raise ContextError("invalid entry:\n- " + "\n- ".join(errors))
        print(json.dumps({"ok": True, "check": True, "record_type": entry["record_type"], "scope": entry["scope"],
                          "sections": sorted(k for k in entry if k not in {"version", "timestamp", "entry_id", "agent", "repository", "record_type", "importance", "scope", "context"})}))
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with file_lock(path):
        entries = load_entries(root, cfg)
        if key:
            prior = next((e for e in entries if e.get("idempotency_key") == key), None)
            if prior:
                if prior.get("idempotency_digest") != digest:
                    raise ContextError("idempotency key already used for a different semantic payload")
                print(json.dumps({"entry_id": prior["entry_id"], "timestamp": prior["timestamp"], "record_type": prior["record_type"], "replayed": True}))
                return 0
        validate_relations(payload, entries)
        entry = build_entry(
            root,
            cfg,
            payload,
            agent,
            args.session_id,
            override,
            entries=entries,
            allow_empty_coverage=bool(getattr(args, "allow_empty_coverage", False)),
        )
        append_entry(root, cfg, entry, already_locked=True)
    try:
        update_runtime_after_checkpoint(root, agent, entry["agent"]["session_id"], entry["entry_id"])
    except OSError as exc:
        eprint(f"ctx: checkpoint persisted as {entry['entry_id']}; runtime update warning: {exc}")
    result = {"entry_id": entry["entry_id"], "timestamp": entry["timestamp"], "record_type": entry["record_type"]}
    threshold = max(1, int(cfg.get("reflection", {}).get("suggest_after_observations", 20)))
    for scope in entry["scope"] or ["project"]:
        all_records = [*entries, entry]
        covered = covered_entry_ids(all_records, [scope])
        count = sum(e.get("record_type") in {"observation", "handoff"} and e.get("entry_id") not in covered and matches_scope(e, [scope]) for e in all_records)
        if count and count % threshold == 0:
            result["reflection_hint"] = f"{count} uncovered records in {scope}; ctx reflect --prepare --scope {scope}"
            break
    print(json.dumps(result))
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
            "turn_checkpointed": True,
        }
    )
    write_json_atomic(state_path, state)
    print(f"acknowledged non-durable turn for session {sid}: {args.reason}")
    return 0


def cmd_due(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    agent = args.agent or os.environ.get("PROJECT_CONTEXT_AGENT") or "unknown"
    data = {"cwd": str(root), "session_id": args.session_id or resolve_session_id(root, agent, None)}
    due, reason = checkpoint_due(root, cfg, agent, data)
    result = {"due": due, "reason": reason, "stop_gate": cfg.get("checkpoint", {}).get("stop_gate", "off")}
    if args.json:
        print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    else:
        print(("due" if due else "not due") + ": " + reason)
    return 1 if due else 0


def cmd_validate(args: argparse.Namespace) -> int:
    root, cfg = repo_and_config(args)
    path = log_path(root, cfg)
    if not path.exists():
        print("valid: 0 entries")
        return 0
    errors: list[str] = []
    count = 0
    records: list[tuple[int, dict[str, Any]]] = []
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
            records.append((lineno, entry))
            for error in validate_entry(entry):
                errors.append(f"line {lineno}: {error}")
    identifiers: dict[str, int] = {}
    for lineno, entry in records:
        entry_id = entry.get("entry_id")
        if isinstance(entry_id, str):
            if entry_id in identifiers:
                errors.append(f"line {lineno}: duplicate entry_id also used on line {identifiers[entry_id]}")
            else:
                identifiers[entry_id] = lineno
    for lineno, entry in records:
        coverage = entry.get("coverage")
        if not isinstance(coverage, dict):
            continue
        references = [coverage.get("from_entry_id"), coverage.get("through_entry_id")]
        references.extend(coverage.get("supporting_entry_ids", []) or [])
        for reference in references:
            if isinstance(reference, str) and reference not in identifiers:
                errors.append(f"line {lineno}: coverage references unknown entry_id {reference}")
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
    current = active_entries(entries)
    counts = {kind: sum(1 for e in entries if e.get("record_type") == kind) for kind in sorted(RECORD_TYPES)}
    last_ref = latest_reflection(entries)
    covered = covered_entry_ids(current)
    uncovered = [e for e in current if e.get("record_type") in {"observation", "handoff"} and e.get("entry_id") not in covered]
    since_ref = len(uncovered)
    threshold = int(cfg.get("reflection", {}).get("suggest_after_observations", 20))
    names = sorted({scope for e in current for scope in e.get("scope", []) or ["project"]})
    scope_counts: dict[str, int] = {}
    scope_tokens: dict[str, int] = {}
    for scope in names:
        scope_covered = covered_entry_ids(current, None if scope == "project" else [scope])
        remaining = [e for e in current if e.get("record_type") in {"observation", "handoff"} and matches_scope(e, None if scope == "project" else [scope]) and e.get("entry_id") not in scope_covered]
        scope_counts[scope] = len(remaining)
        scope_tokens[scope] = sum(len(format_entry(e)) for e in remaining) // 4
    suggested = [scope for scope in names if scope_counts[scope] >= threshold or scope_tokens[scope] > int(cfg.get("retrieval", {}).get("token_budget", 3000)) * 2]
    data = {
        "reflection_suggested_scopes": suggested,
        "uncovered_by_scope": scope_counts,
        "uncovered_tokens_by_scope": scope_tokens,
        "uncovered_estimated_tokens": sum(len(format_entry(e)) for e in uncovered) // 4,
        "entries": len(entries),
        "record_types": counts,
        "observations_since_reflection": since_ref,
        "reflection_suggested": bool(suggested),
        "log_bytes": log_path(root, cfg).stat().st_size if log_path(root, cfg).exists() else 0,
        "latest_entry": entries[-1].get("timestamp") if entries else None,
        "latest_reflection": last_ref.get("timestamp") if last_ref else None,
    }
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def doctor_health(args: argparse.Namespace) -> int:
    root = discover_repo(getattr(args, "cwd", None))
    host = args.host or os.environ.get("PROJECT_CONTEXT_AGENT", "unknown")
    manifest = read_json(skill_root() / "adapters" / "HOSTS.json", {}) or {}
    details = (manifest.get("hosts") or {}).get(host, {})
    cfg = load_config(root, require_enabled=False) if root else None
    health: dict[str, Any] = {"package_version": PACKAGE_VERSION, "protocol_version": PROTOCOL_VERSION,
                              "host": host, "initialized": bool(cfg), "self_test": "not_requested"}
    if root and cfg:
        runtime = runtime_location(root)
        parent = runtime
        while not parent.exists():
            parent = parent.parent
        ledger = log_path(root, cfg)
        ledger_parent = ledger.parent
        while not ledger_parent.exists():
            ledger_parent = ledger_parent.parent
        hook_raw = details.get("lifecycle", {}).get("project")
        hook = (root / hook_raw) if hook_raw else None
        try:
            # Import by path works both as `python scripts/ctx.py` and as a module.
            import importlib.util
            spec = importlib.util.spec_from_file_location("ctx_install_health", skill_root() / "scripts" / "install.py")
            installer = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(installer)
            profile = installer.installed_hook_profile(host, hook)
        except (OSError, ValueError, RuntimeError, AttributeError):
            profile = "unknown"
        health.update({"hook_profile": profile, "runtime_path": str(runtime), "runtime_writable": os.access(parent, os.W_OK),
                       "ledger_writable": os.access(ledger if ledger.exists() else ledger_parent, os.W_OK),
                       "lifecycle_present": bool(hook and hook.exists()), "hook_path": str(hook) if hook else None,
                       "checkpoint_gate": cfg["checkpoint"]["stop_gate"],
                       "activation_required": details.get("lifecycle", {}).get("activation_required", False),
                       "trust_required": details.get("lifecycle", {}).get("trust_required_project", False)})
        sessions = [read_json(p, {}) for p in runtime.glob("session-*.json")] if runtime.exists() else []
        sessions = [x for x in sessions if x.get("host") == host]
        latest = max(sessions, key=lambda x: x.get("last_emitted_at", ""), default={})
        health["last_emission"] = {k: latest[k] for k in ("session_id", "last_emitted_at", "packet_hash", "packet_estimated_tokens", "delivery_status") if k in latest}
        health["diagnosis"] = "configured; host consumption is unverified" if health["lifecycle_present"] else "no project lifecycle configuration; check user installation or use explicit ctx startup"
        if args.self_test:
            errors = [error for e in load_entries(root, cfg) for error in validate_entry(e)]
            packet = context_packet(root, cfg, token_budget=300)
            health["self_test"] = "passed" if not errors and len(packet) <= approx_char_budget(300) else "failed"
            health["errors"] = errors[:5]
    print(json.dumps(health, ensure_ascii=False, indent=2))
    return int(health.get("self_test") == "failed")


def cmd_doctor(args: argparse.Namespace) -> int:
    if args.host or args.json or args.self_test:
        return doctor_health(args)
    root = discover_repo(getattr(args, "cwd", None))
    print(f"project-context {PACKAGE_VERSION} / protocol {PROTOCOL_VERSION}")
    print(f"python: {sys.version.split()[0]}")
    print(f"skill root: {skill_root()}")
    manifest = read_json(skill_root() / "adapters" / "HOSTS.json", {}) or {}
    for host, details in (manifest.get("hosts") or {}).items():
        skills = details.get("skills", {}) if isinstance(details, dict) else {}
        user_raw = skills.get("user")
        project_raw = skills.get("project")
        user_path = pathlib.Path(str(user_raw)).expanduser() if user_raw else None
        project_path = root / str(project_raw) if root and project_raw else None
        present = bool((user_path and user_path.exists()) or (project_path and project_path.exists()))
        lifecycle = details.get("lifecycle", {})
        lifecycle_raw = lifecycle.get("project" if root else "user")
        lifecycle_path = None
        if lifecycle_raw:
            lifecycle_path = pathlib.Path(str(lifecycle_raw)).expanduser()
            if root and not lifecycle_path.is_absolute():
                lifecycle_path = root / lifecycle_path
        flags = []
        if root and lifecycle.get("trust_required_project"):
            flags.append("trust-required")
        if lifecycle.get("activation_required"):
            flags.append("activation-required")
        invocation = details.get("invocation", {}).get("primary", "unknown")
        print(
            f"{host} skill: {'present' if present else 'missing'}; invoke: {invocation}; "
            f"lifecycle: {'present' if lifecycle_path and lifecycle_path.exists() else 'missing'}"
            + (f"; {','.join(flags)}" if flags else "")
        )
    if not root:
        print("repo: not inside a Git repository")
        return 0
    print(f"repo: {root}")
    linked, common = linked_worktree(root)
    if linked:
        print(f"worktree: linked (common Git dir: {common}) — repo-mode storage is separate from the main checkout's; git-common storage shares one ledger")
    cfg = load_config(root, require_enabled=False)
    print(f"config: {'present' if config_path(root).exists() else 'missing'}")
    if not cfg:
        print("project-context: not initialized")
        return 0
    lp = log_path(root, cfg)
    print(f"enabled: {cfg.get('enabled', True)}")
    print(f"log: {lp} ({lp.stat().st_size if lp.exists() else 0} bytes)")
    print(f"storage_mode: {cfg.get('storage', {}).get('mode', 'repo')}")
    print(f"tracking_policy: {cfg.get('storage', {}).get('tracking', 'unmanaged')}")
    print(f"checkpoint_stop_gate: {cfg.get('checkpoint', {}).get('stop_gate', 'off')}")
    legacy_reflections = sum(
        1 for entry in load_entries(root, cfg, strict=False)
        if entry.get("record_type") == "reflection"
        and isinstance(entry.get("coverage"), dict)
        and "scope" not in entry["coverage"]
    )
    if legacy_reflections:
        print(f"warning: {legacy_reflections} legacy reflections have no coverage.scope; they remain readable but should not be treated as global watermarks")
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
    parser.add_argument("--path", action="append", help="repo-relative path/prefix")
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
    parser.add_argument("--json-errors", action="store_true", help="structured JSON Pointer validation diagnostics on stderr")
    parser.add_argument("--idempotency-key", help="stable unique key for retry-safe append")
    parser.add_argument("--check", action="store_true", help="build and validate the record, write nothing (no ledger append, no runtime state)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ctx", description="Shared append-only project memory for coding agents")
    parser.add_argument("--version", action="version", version=f"project-context {PACKAGE_VERSION} protocol {PROTOCOL_VERSION}")
    parser.add_argument("--cwd", help="operate as if launched from this directory")
    subs = parser.add_subparsers(dest="command", required=True)

    p = subs.add_parser("init", help="initialize project-context in the current Git repository")
    p.add_argument("--instructions", action="store_true", help="add/update AGENTS.md bootstrap and CLAUDE.md import")
    p.add_argument("--stop-check", action="store_true", help="enable Stop hook enforcement in project config")
    p.add_argument("--checkpoint-gate", choices=sorted(CHECKPOINT_GATES), help="checkpoint requirement enforced by compatible Stop hooks")
    p.add_argument("--storage", choices=sorted(STORAGE_MODES), help="ledger storage mode")
    p.add_argument("--storage-path", help="custom ledger path; absolute for external storage")
    p.add_argument("--tracking", choices=sorted(TRACKING_POLICIES), help="Git tracking policy for repo storage")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = subs.add_parser("startup", help="render bounded startup context")
    p.add_argument("--scope", action="append")
    p.add_argument("--path", action="append")
    p.add_argument("--budget", type=int)
    p.add_argument("--compact", action="store_true")
    p.add_argument("--delivery", action="store_true", help="session-specific emission deduplication for adapters")
    p.add_argument("--session-id")
    p.add_argument("--agent")
    p.set_defaults(func=cmd_startup)

    p = subs.add_parser("context", help="render reflection + relevant tail for a scope/path")
    p.add_argument("--scope", action="append")
    p.add_argument("--path", action="append")
    p.add_argument("--budget", type=int)
    p.add_argument("--explain", action="store_true", help="show selected entry IDs and selection reasons")
    p.add_argument("--session", help="only records from this agent session id (an orchestrated run records itself under its run id)")
    p.add_argument("--task", help="only records whose task.id matches")
    p.add_argument("--query", help="rank memory by task text within explicit filters")
    p.add_argument("--history", action="store_true")
    p.set_defaults(func=cmd_context)

    p = subs.add_parser("search", help="local ranked lexical search; no embeddings or network")
    p.add_argument("query")
    add_common_query(p)
    p.add_argument("--history", action="store_true")
    p.set_defaults(func=cmd_search)

    p = subs.add_parser("scopes", help="discover scope labels, counts and paths")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_scopes)

    p = subs.add_parser("show", help="expand one source ID, or one section")
    p.add_argument("entry_id")
    p.add_argument("--section")
    p.add_argument("--json", action="store_true")
    p.add_argument("--budget", type=int, default=3000)
    p.set_defaults(func=cmd_show)

    p = subs.add_parser("template", help="working semantic payload examples")
    p.add_argument("record_type", choices=sorted(RECORD_TYPES))
    p.add_argument("--minimal", action="store_true")
    p.set_defaults(func=cmd_template)

    p = subs.add_parser("schema", help="semantic input schema; metadata is owned by ctx")
    p.add_argument("--section")
    p.add_argument("--stored", action="store_true", help="show persisted entry schema including metadata")
    p.set_defaults(func=cmd_schema)

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
    p.add_argument("--path", action="append")
    p.add_argument("--agent", dest="agent_filter")
    p.add_argument("--session", help="only records from this agent session id")
    p.add_argument("--task", help="only records whose task.id matches")
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

    p = subs.add_parser("attempts", help="project attempts, optionally by outcome; identical approach+outcome across records fold into one line with a count")
    add_common_query(p)
    p.add_argument("--outcome", choices=sorted(ATTEMPT_OUTCOMES))
    p.add_argument("--no-group", action="store_true", help="show every occurrence instead of folding identical approach+outcome")
    p.set_defaults(func=cmd_attempts)

    p = subs.add_parser("open", help="remaining work, blockers, questions, next steps")
    add_common_query(p)
    p.add_argument("--history", action="store_true")
    p.set_defaults(func=cmd_open)

    p = subs.add_parser("blockers", help="current blockers")
    add_common_query(p)
    p.add_argument("--history", action="store_true")
    p.set_defaults(func=cmd_blockers)

    p = subs.add_parser("append", help="append an observation/reflection/handoff from semantic JSON")
    add_append_args(p)
    p.set_defaults(func=lambda a: cmd_append(a, None))

    p = subs.add_parser("handoff", help="append a handoff")
    add_append_args(p)
    p.set_defaults(func=lambda a: cmd_append(a, "handoff"))

    p = subs.add_parser("reflect", help="append a reflection and auto-fill missing coverage boundaries")
    add_append_args(p)
    p.add_argument("--allow-empty-coverage", action="store_true", help="allow a reflection with no unreflected source records in scope")
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--latest", type=int, default=10)
    p.add_argument("--prepare", action="store_true", help="bounded source packet and reflection template; does not append")
    p.add_argument("--budget", type=int, default=3000)
    p.set_defaults(func=cmd_reflect)

    p = subs.add_parser("skip", help="acknowledge changed Git state that has no durable project-context value")
    p.add_argument("--agent")
    p.add_argument("--session-id")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_skip)

    p = subs.add_parser("due", help="report whether the current turn needs a checkpoint")
    p.add_argument("--agent")
    p.add_argument("--session-id")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_due)

    p = subs.add_parser("validate", help="validate all JSONL records")
    p.set_defaults(func=cmd_validate)

    p = subs.add_parser("stats", help="show log/reflection statistics")
    p.set_defaults(func=cmd_stats)

    p = subs.add_parser("doctor", help="check installation and current repository")
    p.add_argument("--host", choices=["claude", "codex", "grok", "opencode", "cursor", "droid", "pi", "antigravity", "hermes", "openclaw"])
    p.add_argument("--json", action="store_true")
    p.add_argument("--self-test", action="store_true", help="check local ledger and packet; does not launch the host")
    p.set_defaults(func=cmd_doctor)

    p = subs.add_parser("hook", help="host lifecycle adapter")
    p.add_argument("event", choices=["session-start", "turn-start", "pre-invocation", "compact-before", "compact-after", "stop", "session-end"])
    p.add_argument("--host", choices=["claude", "codex", "grok", "opencode", "cursor", "droid", "pi", "antigravity", "hermes", "openclaw"], required=True)
    p.set_defaults(func=cmd_hook)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    for field in ("budget", "latest"):
        value = getattr(args, field, None)
        if value is not None and value <= 0:
            parser.error(f"--{field} must be positive")
    if getattr(args, "offset", 0) < 0:
        parser.error("--offset must be non-negative")
    try:
        return int(args.func(args))
    except (ContextError, OSError) as exc:
        if getattr(args, "json_errors", False):
            diagnostics = []
            for line in str(exc).splitlines():
                if line.startswith("- /"):
                    pointer, _, message = line[2:].partition(": ")
                    code, _, detail = message.partition(": ")
                    diagnostics.append({"pointer": pointer, "code": code, "message": detail or message})
            eprint(json.dumps({"ok": False, "error": str(exc).splitlines()[0], "diagnostics": diagnostics}))
        else:
            eprint(f"ctx: {exc}")
        if args.command == "hook":
            if args.host == "antigravity":
                emit_hook_json({"injectSteps": []} if args.event == "pre-invocation" else {})
            elif args.host in {"cursor", "droid", "codex", "claude"}:
                emit_hook_json({})
            return 0
        return 2
    except KeyboardInterrupt:
        eprint("ctx: interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
