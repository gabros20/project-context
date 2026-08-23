# Host adapters

`HOSTS.json` is the machine-readable source of truth for supported host paths, explicit invocation syntax, lifecycle capabilities, trust/activation requirements, and first-party evidence.

The adapter layer intentionally contains **no memory semantics**. Every host maps its native lifecycle to `scripts/ctx.py hook <normalized-event> --host <host>` or invokes `ctx startup` for a host-specific injection surface.

Generated adapter files are rendered from `templates/` by `scripts/install.py`; compact inline fallbacks keep already-installed canonical packages usable if a partial package copy loses the templates. Contract tests validate rendered syntax and required lifecycle markers.
