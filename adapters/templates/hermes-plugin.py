"""Generated project-context lifecycle plugin (hook profile: @@HOOK_PROFILE@@)."""
import json
import os
import subprocess
import sys
import uuid

_FALLBACK_SESSION = "hermes-" + str(uuid.uuid4())

PY=@@PYTHON@@
CTX=@@CTX@@

def _cwd(kwargs): return kwargs.get("cwd") or os.getcwd()
def _safe(args, kwargs, payload=None):
    try:
        process=subprocess.run([PY,CTX,*args],input=json.dumps(payload) if payload is not None else None,text=True,capture_output=True,cwd=_cwd(kwargs),timeout=5)
        if process.returncode:
            print("project-context: " + process.stderr[:300], file=sys.stderr)
        return process.stdout.strip() if process.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("project-context: " + str(exc)[:300], file=sys.stderr)
        return ""

def _session(kwargs): return str(kwargs.get("session_id") or kwargs.get("sessionId") or kwargs.get("session_key") or _FALLBACK_SESSION)

def _run(event, kwargs):
    payload=dict(kwargs); payload.setdefault("cwd", _cwd(kwargs)); payload.setdefault("session_id", _session(kwargs))
    return _safe(["hook",event,"--host","hermes"],kwargs,payload)
def _startup(kwargs):
    session=_session(kwargs)
    return _safe(["--cwd",_cwd(kwargs),"startup","--delivery","--agent","hermes","--session-id",session],kwargs)

def on_start(**kwargs): _run("session-start",kwargs)
def pre_llm_call(is_first_turn=False, **kwargs):
@@TURN_START@@
    if is_first_turn:
        text=_startup(kwargs)
        if text: return {"context": text}
    return None
@@FULL_FUNCTIONS@@

def register(ctx):
    ctx.register_hook("on_session_start", on_start)
    ctx.register_hook("pre_llm_call", pre_llm_call)
@@FULL_REGISTRATIONS@@
