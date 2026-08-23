"""Generated project-context lifecycle plugin."""
import json
import os
import subprocess

PY=@@PYTHON@@
CTX=@@CTX@@

def _cwd(kwargs): return kwargs.get("cwd") or os.getcwd()
def _run(event, kwargs):
    payload=dict(kwargs); payload.setdefault("cwd", _cwd(kwargs))
    process=subprocess.run([PY,CTX,"hook",event,"--host","hermes"],input=json.dumps(payload),text=True,capture_output=True,cwd=_cwd(kwargs))
    return process.stdout.strip()
def _startup(kwargs):
    process=subprocess.run([PY,CTX,"--cwd",_cwd(kwargs),"startup"],text=True,capture_output=True,cwd=_cwd(kwargs))
    return process.stdout.strip() if process.returncode==0 else ""

def on_start(**kwargs): _run("session-start",kwargs)
def pre_llm_call(is_first_turn=False, **kwargs):
    _run("turn-start",kwargs)
    if is_first_turn:
        text=_startup(kwargs)
        if text: return {"context": text}
    return None
def pre_verify(coding=False, attempt=0, **kwargs):
    if not coding or attempt: return None
    output=_run("stop",kwargs)
    if not output: return None
    try: return json.loads(output)
    except Exception: return None
def on_end(**kwargs): _run("session-end",kwargs)

def register(ctx):
    ctx.register_hook("on_session_start", on_start)
    ctx.register_hook("pre_llm_call", pre_llm_call)
    ctx.register_hook("pre_verify", pre_verify)
    ctx.register_hook("on_session_end", on_end)
