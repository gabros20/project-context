#!/usr/bin/env python3
"""Universal installer for project-context skills and lifecycle adapters.

Safety properties:
- Existing JSON is parsed before modification; malformed files are refused.
- Existing unrelated settings/hooks are preserved.
- First pre-project-context content is copied to *.project-context.bak.
- Writes are atomic and repeated installs are idempotent.
- Project scope never writes user/global hook config.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterable

PACKAGE_VERSION = "0.5.0"
SKILL_NAME = "project-context"
SOURCE_ROOT = pathlib.Path(__file__).resolve().parent.parent
HOOK_PROFILES = ("full", "startup-only")


def load_host_manifest() -> dict[str, Any]:
    path = SOURCE_ROOT / "adapters" / "HOSTS.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Cannot load host capability manifest {path}: {exc}") from exc
    if not isinstance(data.get("hosts"), dict):
        raise RuntimeError(f"Host capability manifest has no hosts object: {path}")
    return data


HOST_MANIFEST = load_host_manifest()
HOST_DATA: dict[str, dict[str, Any]] = HOST_MANIFEST["hosts"]
HOSTS = tuple(HOST_DATA)
BINARIES = {name: tuple(data.get("binaries", [])) for name, data in HOST_DATA.items()}
USER_MARKERS = {name: str(data.get("user_marker", "")) for name, data in HOST_DATA.items()}


def source_root() -> pathlib.Path:
    return SOURCE_ROOT


def home() -> pathlib.Path:
    return pathlib.Path.home()


def canonical_root() -> pathlib.Path:
    return home() / ".agent-skills" / SKILL_NAME


def canonical_ctx() -> pathlib.Path:
    return canonical_root() / "scripts" / "ctx.py"


def python_exe() -> str:
    # Prefer an absolute executable for hooks; fall back to python3/python.
    found = shutil.which("python3") or shutil.which("python")
    return found or sys.executable


def runtime_ctx() -> pathlib.Path:
    # A globally installed canonical copy is most stable. If this skill is invoked
    # directly from a host skill directory, its own bundled ctx is self-contained.
    candidate = canonical_ctx()
    if candidate.exists():
        return candidate.resolve()
    return (source_root() / "scripts" / "ctx.py").resolve()


def shell_command(host: str, event: str) -> str:
    return f"{shlex.quote(python_exe())} {shlex.quote(str(runtime_ctx()))} hook {shlex.quote(event)} --host {shlex.quote(host)}"


def read_json(path: pathlib.Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Refusing to modify invalid JSON file {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Refusing to modify non-object JSON file {path}")
    return data


def backup_original(path: pathlib.Path) -> pathlib.Path | None:
    if not path.exists():
        return None
    backup = path.with_name(path.name + ".project-context.bak")
    if not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup)
    return backup


def write_text_atomic(path: pathlib.Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def write_json_if_changed(path: pathlib.Path, data: dict[str, Any]) -> bool:
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    backup_original(path)
    write_text_atomic(path, text)
    return True


def write_generated(path: pathlib.Path, text: str) -> bool:
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    backup_original(path)
    write_text_atomic(path, text)
    return True


def discover_repo(value: str | None = None) -> pathlib.Path:
    base = pathlib.Path(value or os.getcwd()).expanduser().resolve()
    proc = subprocess.run(["git", "-C", str(base), "rev-parse", "--show-toplevel"], text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    if proc.returncode != 0:
        raise RuntimeError(f"Not inside a Git repository: {base}")
    return pathlib.Path(proc.stdout.strip()).resolve()


def copy_package(force: bool = False) -> None:
    src = source_root()
    dst = canonical_root()
    if dst.exists() and src.resolve() == dst.resolve():
        print(f"canonical package already running from {dst}")
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and force:
        shutil.rmtree(dst)
    shutil.copytree(
        src,
        dst,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            ".DS_Store",
            ".git",
            ".github",
            ".pytest_cache",
            ".vercel",
            ".env*",
        ),
    )
    for script in (dst / "scripts").glob("*.py"):
        try:
            script.chmod(script.stat().st_mode | stat.S_IXUSR)
        except OSError:
            pass
    print(f"installed canonical package: {dst}")


def create_link(link: pathlib.Path, target: pathlib.Path, force: bool = False) -> bool:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink():
        try:
            if link.resolve() == target.resolve():
                return False
        except OSError:
            pass
        if not force:
            print(f"skip existing symlink: {link}")
            return False
        link.unlink()
    elif link.exists():
        if not force:
            print(f"skip existing skill path: {link}")
            return False
        backup = link.with_name(link.name + ".project-context.bak")
        if not backup.exists():
            if link.is_dir():
                shutil.copytree(link, backup)
            else:
                shutil.copy2(link, backup)
        if link.is_dir():
            shutil.rmtree(link)
        else:
            link.unlink()
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        shutil.copytree(target, link, dirs_exist_ok=True)
    print(f"skill: {link}")
    return True


def install_launcher() -> None:
    target = canonical_ctx() if canonical_ctx().exists() else runtime_ctx()
    if os.name == "nt":
        path = home() / "bin" / "ctx.cmd"
        text = f'@echo off\r\n"{python_exe()}" "{target}" %*\r\n'
    else:
        path = home() / ".local" / "bin" / "ctx"
        text = f'#!/bin/sh\nexec {shlex.quote(python_exe())} {shlex.quote(str(target))} "$@"\n'
    changed = write_generated(path, text)
    if os.name != "nt":
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"launcher: {path}{' (updated)' if changed else ''}")


def detect_hosts() -> list[str]:
    result: list[str] = []
    for host_name in HOSTS:
        bin_found = any(shutil.which(name) for name in BINARIES[host_name])
        marker = home() / USER_MARKERS[host_name]
        if bin_found or marker.exists():
            result.append(host_name)
    return result


def parse_hosts(value: str) -> list[str]:
    value = value.strip().lower()
    if value == "all":
        return list(HOSTS)
    if value == "auto":
        found = detect_hosts()
        if not found:
            raise RuntimeError("No supported hosts detected. Use --hosts <comma-separated names> or --hosts all.")
        return found
    names = [x.strip() for x in value.split(",") if x.strip()]
    bad = [x for x in names if x not in HOSTS]
    if bad:
        raise RuntimeError(f"Unknown hosts: {', '.join(bad)}. Supported: {', '.join(HOSTS)}")
    return list(dict.fromkeys(names))


# ---------- skill locations ----------

def manifest_path(value: str | None, root: pathlib.Path | None = None) -> pathlib.Path | None:
    if not value:
        return None
    if value.startswith("~/"):
        return home() / value[2:]
    path = pathlib.Path(value)
    if path.is_absolute():
        return path
    if root is None:
        raise RuntimeError(f"Project root required to resolve {value}")
    return root / path

def user_skill_path(host_name: str) -> pathlib.Path:
    path = manifest_path(str(HOST_DATA[host_name]["skills"]["user"]))
    assert path is not None
    return path


def project_skill_path(host_name: str, root: pathlib.Path) -> pathlib.Path | None:
    return manifest_path(HOST_DATA[host_name]["skills"].get("project"), root)


def install_skills(hosts: list[str], scope: str, root: pathlib.Path | None, force: bool) -> None:
    target = canonical_root() if canonical_root().exists() else source_root()
    # Generic Agent Skills path gives Codex/OpenCode/Pi/OpenClaw and other compatible hosts a shared copy.
    if scope == "user":
        create_link(home() / ".agents/skills/project-context", target, force)
    for host_name in hosts:
        path = user_skill_path(host_name) if scope == "user" else project_skill_path(host_name, root or discover_repo())
        if path is None:
            print(f"{host_name}: no documented project-local skill root; use the user skill and project AGENTS.md")
            continue
        create_link(path, target, force)


# ---------- JSON hook merging ----------

def group(command: str, *, matcher: str | None = None, timeout: int = 10, **extra: Any) -> dict[str, Any]:
    handler: dict[str, Any] = {"type": "command", "command": command, "timeout": timeout}
    handler.update(extra)
    result: dict[str, Any] = {"hooks": [handler]}
    if matcher is not None:
        result["matcher"] = matcher
    return result


def managed_command_event(value: Any, host_name: str) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parts = shlex.split(value)
    except ValueError:
        return None
    for index, part in enumerate(parts[:-1]):
        if pathlib.Path(part).name != "ctx.py" or parts[index + 1] != "hook":
            continue
        try:
            if parts[parts.index("--host", index + 2) + 1] == host_name:
                return parts[index + 2]
        except (ValueError, IndexError):
            return None
    return None


def is_managed_command(value: Any, host_name: str) -> bool:
    return managed_command_event(value, host_name) is not None


def strip_managed_group_hooks(target: dict[str, Any], host_name: str) -> None:
    for event in list(target):
        groups = target[event]
        if not isinstance(groups, list):
            continue
        kept_groups: list[Any] = []
        for item in groups:
            if not isinstance(item, dict) or not isinstance(item.get("hooks"), list):
                kept_groups.append(item)
                continue
            kept_handlers = [
                handler for handler in item["hooks"]
                if not (isinstance(handler, dict) and is_managed_command(handler.get("command"), host_name))
            ]
            if kept_handlers:
                updated = dict(item)
                updated["hooks"] = kept_handlers
                kept_groups.append(updated)
        if kept_groups:
            target[event] = kept_groups
        else:
            target.pop(event)


def reconcile_group_hooks(
    config: dict[str, Any],
    additions: dict[str, list[dict[str, Any]]],
    host_name: str,
    wrapped: bool = True,
) -> bool:
    before = json.dumps(config, ensure_ascii=False, sort_keys=True)
    target = config.setdefault("hooks", {}) if wrapped else config
    if not isinstance(target, dict):
        raise RuntimeError("Existing hooks value is not a JSON object")
    strip_managed_group_hooks(target, host_name)
    for event, groups in additions.items():
        existing = target.setdefault(event, [])
        if not isinstance(existing, list):
            raise RuntimeError(f"Existing {event} hook value is not an array")
        existing.extend(groups)
    return before != json.dumps(config, ensure_ascii=False, sort_keys=True)


def claude_codex_hooks(host_name: str, profile: str) -> dict[str, list[dict[str, Any]]]:
    hooks = {
        "SessionStart": [group(shell_command(host_name, "session-start"), matcher="startup|resume|clear|compact", timeout=10,
                               statusMessage="Loading project context", additionalContextLimit=3200)],
    }
    if profile == "full":
        hooks.update({
            "UserPromptSubmit": [group(shell_command(host_name, "turn-start"), timeout=5)],
            "Stop": [group(shell_command(host_name, "stop"), timeout=10)],
            "SessionEnd": [group(shell_command(host_name, "session-end"), timeout=3)],
        })
    return hooks


def grok_hooks(profile: str) -> dict[str, Any]:
    hooks = {
        "SessionStart": [group(shell_command("grok", "session-start"), timeout=10)],
    }
    if profile == "full":
        hooks.update({
            "UserPromptSubmit": [group(shell_command("grok", "turn-start"), timeout=5)],
            "PreCompact": [group(shell_command("grok", "compact-before"), timeout=5)],
            "PostCompact": [group(shell_command("grok", "compact-after"), timeout=5)],
            "Stop": [group(shell_command("grok", "stop"), timeout=5)],
            "SessionEnd": [group(shell_command("grok", "session-end"), timeout=3)],
        })
    return {"hooks": hooks}


def cursor_hooks(profile: str) -> dict[str, list[dict[str, Any]]]:
    hooks = {
        "sessionStart": [{"command": shell_command("cursor", "session-start")}],
    }
    if profile == "full":
        hooks.update({
            "beforeSubmitPrompt": [{"command": shell_command("cursor", "turn-start")}],
            "preCompact": [{"command": shell_command("cursor", "compact-before")}],
            "stop": [{"command": shell_command("cursor", "stop"), "loop_limit": 2}],
            "sessionEnd": [{"command": shell_command("cursor", "session-end")}],
        })
    return hooks


def merge_cursor(config: dict[str, Any], profile: str) -> bool:
    before = json.dumps(config, ensure_ascii=False, sort_keys=True)
    if "version" not in config:
        config["version"] = 1
    hooks = config.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise RuntimeError("Existing Cursor hooks value is not an object")
    for event in list(hooks):
        handlers = hooks[event]
        if not isinstance(handlers, list):
            continue
        kept = [
            handler for handler in handlers
            if not (isinstance(handler, dict) and is_managed_command(handler.get("command"), "cursor"))
        ]
        if kept:
            hooks[event] = kept
        else:
            hooks.pop(event)
    for event, handlers in cursor_hooks(profile).items():
        existing = hooks.setdefault(event, [])
        if not isinstance(existing, list):
            raise RuntimeError(f"Existing Cursor hooks.{event} is not an array")
        existing.extend(handlers)
    return before != json.dumps(config, ensure_ascii=False, sort_keys=True)


def droid_hooks(profile: str) -> dict[str, list[dict[str, Any]]]:
    hooks = {
        "SessionStart": [group(shell_command("droid", "session-start"), timeout=10)],
    }
    if profile == "full":
        hooks.update({
            "UserPromptSubmit": [group(shell_command("droid", "turn-start"), timeout=5)],
            "PreCompact": [group(shell_command("droid", "compact-before"), timeout=5)],
            "Stop": [group(shell_command("droid", "stop"), timeout=10)],
            "SessionEnd": [group(shell_command("droid", "session-end"), timeout=3)],
        })
    return hooks


def antigravity_hook_definition(profile: str) -> dict[str, Any]:
    hooks = {
        "PreInvocation": [{"type": "command", "command": shell_command("antigravity", "pre-invocation"), "timeout": 10}],
    }
    if profile == "full":
        hooks["Stop"] = [{"type": "command", "command": shell_command("antigravity", "stop"), "timeout": 10}]
    return hooks


def antigravity_definition_is_managed(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return any(
        isinstance(handler, dict) and is_managed_command(handler.get("command"), "antigravity")
        for handlers in value.values() if isinstance(handlers, list)
        for handler in handlers
    )


def merge_antigravity(config: dict[str, Any], profile: str) -> bool:
    before = json.dumps(config, ensure_ascii=False, sort_keys=True)
    wanted = antigravity_hook_definition(profile)
    primary = "project-context"
    fallback = "project-context-universal"
    if antigravity_definition_is_managed(config.get(primary)):
        config[primary] = wanted
        if antigravity_definition_is_managed(config.get(fallback)):
            config.pop(fallback)
    elif config.get(primary) is None:
        config[primary] = wanted
    else:
        config[fallback] = wanted
    return before != json.dumps(config, ensure_ascii=False, sort_keys=True)


def json_hook_path(host_name: str, scope: str, root: pathlib.Path | None) -> pathlib.Path | None:
    lifecycle = HOST_DATA[host_name].get("lifecycle", {})
    if lifecycle.get("mechanism") not in {"command-hooks", "native-hooks-json"}:
        return None
    return manifest_path(lifecycle.get(scope), root)


def install_json_host(host_name: str, scope: str, root: pathlib.Path | None, profile: str) -> pathlib.Path:
    path = json_hook_path(host_name, scope, root)
    assert path is not None
    data = read_json(path)
    changed = False
    if host_name in {"claude", "codex"}:
        changed = reconcile_group_hooks(data, claude_codex_hooks(host_name, profile), host_name, wrapped=True)
    elif host_name == "grok":
        # dedicated file owned by project-context, but preserve any user additions in it
        changed = reconcile_group_hooks(data, grok_hooks(profile)["hooks"], host_name, wrapped=True)
    elif host_name == "cursor":
        changed = merge_cursor(data, profile)
    elif host_name == "droid":
        changed = reconcile_group_hooks(data, droid_hooks(profile), host_name, wrapped=False)
    elif host_name == "antigravity":
        changed = merge_antigravity(data, profile)
    if changed or not path.exists():
        write_json_if_changed(path, data)
        print(f"{host_name}: {profile} hooks installed -> {path}")
    else:
        print(f"{host_name}: {profile} hooks already installed -> {path}")
    return path


# ---------- generated adapters ----------

def js_string(value: str) -> str:
    return json.dumps(value)


def render_adapter_template(name: str, **values: str) -> str:
    path = source_root() / "adapters" / "templates" / name
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Cannot read adapter template {path}: {exc}") from exc
    for key, value in values.items():
        text = text.replace(f"@@{key}@@", value)
    unresolved = sorted(set(re.findall(r"@@[A-Z_]+@@", text)))
    if unresolved:
        raise RuntimeError(f"Unresolved adapter template values in {path}: {', '.join(unresolved)}")
    return text


def opencode_command() -> str:
    return '''---
description: Checkpoint or retrieve shared project context
---

Load the `project-context` skill and execute it as an explicit user invocation.
Treat no arguments as a request to checkpoint the current session.
Arguments from the user: $ARGUMENTS
'''


def templated_opencode_plugin(profile: str) -> str:
    full_events = '''    if(event.type==="session.idle") run(["hook","stop","--host","opencode"],base,directory);
    if(event.type==="session.compacted") run(["hook","compact-after","--host","opencode"],base,directory);
    if(event.type==="session.deleted") run(["hook","session-end","--host","opencode"],base,directory);''' if profile == "full" else ""
    compact_before = '    run(["hook","compact-before","--host","opencode"],{cwd:worktree||directory,session_id:input?.sessionID||"opencode-runtime"},directory);' if profile == "full" else ""
    return render_adapter_template(
        "opencode-plugin.js", PACKAGE_VERSION=PACKAGE_VERSION,
        PYTHON=js_string(python_exe()), CTX=js_string(str(runtime_ctx())),
        HOOK_PROFILE=profile, FULL_EVENT_HANDLERS=full_events, COMPACT_BEFORE=compact_before,
    )


def templated_pi_extension(profile: str) -> str:
    turn_start = '    run("turn-start",{},c.cwd);' if profile == "full" else ""
    lifecycle = '''  pi.on("session_before_compact", async (_event,c)=>{ run("compact-before",{},c.cwd); });
  pi.on("session_compact", async (_event,c)=>{ run("compact-after",{},c.cwd); injected=false; });
  pi.on("agent_settled", async (_event,c)=>{ run("stop",{},c.cwd); });
  pi.on("session_shutdown", async (_event,c)=>{ run("session-end",{},c.cwd); });''' if profile == "full" else '  pi.on("session_compact", async (_event,c)=>{ injected=false; });'
    return render_adapter_template(
        "pi-extension.ts", PACKAGE_VERSION=PACKAGE_VERSION,
        PYTHON=js_string(python_exe()), CTX=js_string(str(runtime_ctx())),
        HOOK_PROFILE=profile, TURN_START=turn_start, LIFECYCLE_HANDLERS=lifecycle,
    )


def templated_hermes_plugin_files(profile: str) -> dict[str, str]:
    full_functions = '''def pre_verify(coding=False, attempt=0, **kwargs):
    if not coding or attempt: return None
    output=_run("stop",kwargs)
    if not output: return None
    try: return json.loads(output)
    except Exception: return None
def on_end(**kwargs): _run("session-end",kwargs)''' if profile == "full" else ""
    values = {
        "PACKAGE_VERSION": PACKAGE_VERSION,
        "PYTHON": repr(python_exe()),
        "CTX": repr(str(runtime_ctx())),
        "HOOK_PROFILE": profile,
        "TURN_START": '    _run("turn-start",kwargs)' if profile == "full" else "",
        "FULL_FUNCTIONS": full_functions,
        "FULL_REGISTRATIONS": '    ctx.register_hook("pre_verify", pre_verify)\n    ctx.register_hook("on_session_end", on_end)' if profile == "full" else "",
    }
    return {
        "plugin.yaml": render_adapter_template("hermes-plugin.yaml", **values),
        "__init__.py": render_adapter_template("hermes-plugin.py", **values),
    }


def templated_openclaw_hook_files(profile: str) -> dict[str, str]:
    events = ["agent:bootstrap"]
    full_lifecycle = ""
    if profile == "full":
        events.extend(["session:compact:before", "session:compact:after", "command:new", "command:reset", "session:auto-reset"])
        full_lifecycle = '''  if(event.type==="session" && event.action==="compact:before") run("compact-before");
  if(event.type==="session" && event.action==="compact:after") run("compact-after");
  if((event.type==="command" && (event.action==="new"||event.action==="reset")) || (event.type==="session"&&event.action==="auto-reset")) run("session-end");'''
    values = {
        "PYTHON": js_string(python_exe()), "CTX": js_string(str(runtime_ctx())),
        "HOOK_PROFILE": profile, "EVENTS": json.dumps(events, separators=(",", ":")),
        "FULL_LIFECYCLE": full_lifecycle,
    }
    return {
        "HOOK.md": render_adapter_template("openclaw-HOOK.md", **values),
        "handler.js": render_adapter_template("openclaw-handler.js", **values),
    }


def install_generated_host(host_name: str, scope: str, root: pathlib.Path | None, profile: str) -> list[pathlib.Path]:
    lifecycle_path = manifest_path(HOST_DATA[host_name]["lifecycle"].get(scope), root)
    if lifecycle_path is None:
        raise RuntimeError(f"No {scope} lifecycle location is documented for {host_name}")
    if host_name == "opencode":
        path = lifecycle_path
        command = (root / ".opencode/commands/project-context.md" if scope == "project" else home() / ".config/opencode/commands/project-context.md")
        write_generated(path, templated_opencode_plugin(profile)); write_generated(command, opencode_command()); return [path, command]
    if host_name == "pi":
        path = lifecycle_path
        write_generated(path, templated_pi_extension(profile)); return [path]
    if host_name == "hermes":
        base = lifecycle_path
        out=[]
        for name,text in templated_hermes_plugin_files(profile).items():
            p=base/name; write_generated(p,text); out.append(p)
        return out
    if host_name == "openclaw":
        base = lifecycle_path
        out=[]
        for name,text in templated_openclaw_hook_files(profile).items():
            p=base/name; write_generated(p,text); out.append(p)
        return out
    raise RuntimeError(host_name)


def activation_notes(host_name: str, scope: str) -> list[str]:
    notes=[]
    if host_name == "codex": notes.append("Open Codex /hooks and trust the new or changed hook definitions.")
    if host_name == "grok" and scope == "project": notes.append("Project hooks require Grok trust: use /hooks-trust or launch with --trust.")
    if host_name == "cursor" and scope == "project": notes.append("Cursor project hooks run only in trusted workspaces.")
    if host_name == "droid": notes.append("Review effective hooks in Droid with /hooks.")
    if host_name == "hermes":
        notes.append("Enable the plugin with: hermes plugins enable project-context")
        if scope == "project": notes.append("Project Hermes plugins also require HERMES_ENABLE_PROJECT_PLUGINS=1.")
    if host_name == "openclaw": notes.append("Enable/check the hook with: openclaw hooks enable project-context && openclaw hooks check")
    return notes


def maybe_activate(host_name: str) -> None:
    if host_name == "hermes" and shutil.which("hermes"):
        subprocess.run(["hermes", "plugins", "enable", "project-context"], check=False)
    elif host_name == "openclaw" and shutil.which("openclaw"):
        subprocess.run(["openclaw", "hooks", "enable", "project-context"], check=False)


def install_hooks(hosts: list[str], scope: str, root: pathlib.Path | None, activate: bool, profile: str) -> None:
    if scope == "project" and root is None:
        root = discover_repo()
    for host_name in hosts:
        try:
            if host_name in {"claude","codex","grok","cursor","droid","antigravity"}:
                paths=[install_json_host(host_name, scope, root, profile)]
            else:
                paths=install_generated_host(host_name, scope, root, profile)
                print(f"{host_name}: {profile} lifecycle adapter -> {', '.join(str(p) for p in paths)}")
            if activate:
                maybe_activate(host_name)
            for note in activation_notes(host_name, scope):
                print(f"  note: {note}")
        except Exception as exc:
            raise RuntimeError(f"{host_name}: {exc}") from exc


# ---------- status ----------

def installed_hook_profile(host_name: str, path: pathlib.Path | None) -> str:
    if not path or not path.exists():
        return "none"
    mechanism = str((HOST_DATA[host_name].get("lifecycle") or {}).get("mechanism", ""))
    if mechanism.startswith("generated"):
        candidates = [path] if path.is_file() else sorted(item for item in path.iterdir() if item.is_file())
        for candidate in candidates:
            try:
                text = candidate.read_text(encoding="utf-8")
            except OSError:
                continue
            match = re.search(r"hook profile: (startup-only|full)", text)
            if match:
                return match.group(1)
        return "unknown"
    try:
        data = read_json(path)
    except RuntimeError:
        return "invalid"
    events: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            event = managed_command_event(value.get("command"), host_name)
            if event:
                events.append(event)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(data)
    if not events:
        return "unknown"
    return "full" if any(event not in {"session-start", "pre-invocation"} for event in events) else "startup-only"

def status(hosts: list[str], scope: str, root: pathlib.Path | None) -> None:
    if scope == "project" and root is None:
        root = discover_repo()
    print(f"project-context installer {PACKAGE_VERSION}")
    print(f"scope: {scope}")
    if root: print(f"project: {root}")
    for h in hosts:
        skill = user_skill_path(h) if scope=="user" else project_skill_path(h, root or discover_repo())
        hook_path = manifest_path(HOST_DATA[h].get("lifecycle", {}).get(scope), root)
        invocation = HOST_DATA[h].get("invocation", {}).get("primary", "unknown")
        trust = " trust-required" if scope == "project" and HOST_DATA[h].get("lifecycle", {}).get("trust_required_project") else ""
        activation = " activation-required" if HOST_DATA[h].get("lifecycle", {}).get("activation_required") else ""
        profile = installed_hook_profile(h, hook_path)
        print(f"{h:12} skill={'yes' if skill and skill.exists() else 'no ':3} lifecycle={'yes' if hook_path and hook_path.exists() else 'no ':3} profile={profile:12} invoke={invocation}{trust}{activation}  {hook_path or ''}")


def cmd_detect(_args: argparse.Namespace) -> int:
    found=detect_hosts()
    print(json.dumps({"supported": list(HOSTS), "detected": found}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p=argparse.ArgumentParser(description="Install the portable project-context skill and capability-specific lifecycle adapters")
    p.add_argument("--version", action="version", version=PACKAGE_VERSION)
    sub=p.add_subparsers(dest="cmd", required=True)

    q=sub.add_parser("install", help="install one canonical user copy, launcher, and user skill links")
    q.add_argument("--hosts", default="auto")
    q.add_argument("--force", action="store_true")
    q.add_argument("--hooks", action="store_true", help="also install user/global lifecycle integrations")
    q.add_argument("--hook-profile", choices=HOOK_PROFILES, default="full",
                   help="lifecycle coverage when --hooks is used (default: full)")
    q.add_argument("--activate", action="store_true")

    for name in ("skills","hooks","status"):
        q=sub.add_parser(name)
        q.add_argument("--hosts", default="auto")
        q.add_argument("--scope", choices=("user","project"), default="project" if name=="hooks" else "user")
        q.add_argument("--project-root")
        if name=="skills": q.add_argument("--force", action="store_true")
        if name=="hooks":
            q.add_argument("--activate", action="store_true")
            q.add_argument("--hook-profile", choices=HOOK_PROFILES, default="full",
                           help="startup-only loads context without prompt/stop hooks; full also tracks turns")
    sub.add_parser("detect")
    return p


def main(argv: list[str] | None=None) -> int:
    args=build_parser().parse_args(argv)
    try:
        if args.cmd=="detect": return cmd_detect(args)
        hosts=parse_hosts(args.hosts)
        root=discover_repo(args.project_root) if getattr(args,"scope",None)=="project" else None
        if args.cmd=="install":
            copy_package(args.force); install_launcher(); install_skills(hosts,"user",None,args.force)
            if args.hooks: install_hooks(hosts,"user",None,args.activate,args.hook_profile)
        elif args.cmd=="skills": install_skills(hosts,args.scope,root,args.force)
        elif args.cmd=="hooks": install_hooks(hosts,args.scope,root,args.activate,args.hook_profile)
        elif args.cmd=="status": status(hosts,args.scope,root)
        return 0
    except RuntimeError as exc:
        print(f"install.py: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
