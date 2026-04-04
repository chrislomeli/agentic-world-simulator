"""
ogar.workflow

Workflow execution abstraction layer.

This package wraps the concept of "run a long-lived workflow"
behind an interface so we can swap implementations:

  - AsyncioWorkflowRunner (stub.py)  — asyncio Tasks + Queues,
    used for local dev and tests before Temporal is wired in.
  - (future) TemporalWorkflowRunner — real Temporal client.

The base interface is in runner.py: WorkflowRunner ABC.
"""