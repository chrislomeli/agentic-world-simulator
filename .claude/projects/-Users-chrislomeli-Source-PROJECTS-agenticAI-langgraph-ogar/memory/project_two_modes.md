---
name: Two operating modes — context provider vs planning partner
description: The system has two valid use cases that share the same infrastructure but differ in what consumes the output
type: project
---

Two modes identified 2026-03-30:

1. **Context Provider** — supports a primary tool (Claude Code, CI, etc.) by maintaining structured project state. The spec is consumed by something else to do better work. Requires tool bindings / MCP for the primary tool to read/write the spec.

2. **Planning Partner** — the conversation engine IS the primary tool. The validated spec is the deliverable (architecture design, strategy, curriculum). No external integrations needed.

**Why:** A simple project (e.g. "learn sight reading in 10 steps") doesn't need this system — a checklist wins. The system justifies itself when there's structural complexity (dependencies, traceability, constraints) AND either a consumer of the context or planning work complex enough that the spec itself is valuable.

**How to apply:** The planning partner mode is the simpler demo path (no MCP needed). Context provider is the advanced case. Both use the same spec/validation/loop infrastructure. The golden demo should probably start with planning partner mode.
