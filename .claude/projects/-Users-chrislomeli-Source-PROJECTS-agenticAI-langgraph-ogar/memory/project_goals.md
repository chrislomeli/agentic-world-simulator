---
name: Project goals and dogfooding strategy
description: The three goals of langgraph-ogar and the plan to use the project itself as the first real-world example
type: project
---

Three goals established 2026-03-30:

1. **Persistent Project Context** — LLM picks up where it left off across sessions
2. **Constrained State Format** — structured, validatable, not free prose
3. **Progressive Demo Platform** — composable, teachable, demo-worthy

**Why:** The user wants to dogfood this system by managing the project itself with it. The canonical spec lives in `src/conversation_engine/fixtures/project_fixtures.py` as `conversation_engine_meta_spec()`.

**How to apply:** When working on this project, reference the spec as the source of truth for what's done, in progress, and pending. Update it as work completes.