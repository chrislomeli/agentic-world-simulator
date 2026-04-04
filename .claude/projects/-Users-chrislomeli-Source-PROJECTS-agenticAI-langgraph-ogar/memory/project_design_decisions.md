---
name: Core design decisions for langgraph-ogar
description: Key architectural decisions about the Goal/Requirement/Step model and the role of LLMs in the system
type: project
---

The project model is a 3-layer hierarchy: Goal → Requirement → Step.

- **Goals**: desired outcomes, stable, rarely change
- **Requirements**: intent/wish list, no status field by design. Requirement satisfaction is *computed* from steps (all realizing steps done = requirement satisfied)
- **Steps**: buildable work items with explicit status (pending/in_progress/done/blocked), percentage, dependency_refs, blocker_refs

**Why:** Requirements come from the "product manager" mindset (pure intent). Steps are what engineers build. Mixing status into requirements conflates intent with progress.

**How to apply:** Never add a status field to RequirementSpec. Query step status to derive requirement progress.

---

A "Capability" layer (between Requirement and Step) was considered and deferred. Steps currently play double duty as both architectural capabilities and work items. If we reach a point where both "Snapshot Facade" (concept) and "Implement snapshot_facade.py" (task) need separate dependency graphs, Capability earns its place. Until then, keep it simple.

---

The LLM's role is *cognitive assistant*, not autonomous agent:
- Deterministic rules handle structural enforcement (integrity rules, completeness)
- LLM handles semantic reasoning (ambiguity, gaps, contradictions, coherence)
- The persistence angle is the core value: a validated ProjectSpecification gives the LLM a compact, proven-coherent project summary across sessions — not a wall of conversation history