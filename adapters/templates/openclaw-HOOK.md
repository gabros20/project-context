---
name: project-context
description: "Inject project-context memory at agent bootstrap and track compaction/session boundaries."
metadata:
  {"openclaw":{"emoji":"🧠","events":["agent:bootstrap","session:compact:before","session:compact:after","command:new","command:reset","session:auto-reset"],"requires":{"bins":["python3"]}}}
---
# Project Context
Generated lifecycle bridge. Semantic memory remains agent-authored through the project-context skill.
