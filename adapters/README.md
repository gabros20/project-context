# Host adapters

`HOSTS.json` is the machine-readable capability manifest for the universal package.

The adapter layer intentionally contains **no memory semantics**. Every host maps its native lifecycle to `scripts/ctx.py hook <normalized-event> --host <host>` or invokes `ctx startup` for a host-specific injection surface.

Generated adapter files are created by `scripts/install.py`; they are not separately maintained source forks.
