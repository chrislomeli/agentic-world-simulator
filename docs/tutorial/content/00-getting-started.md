# Getting Started: Project Setup

> **What you'll build:** A clean development environment with all dependencies installed and verified.
> **Why you need it:** Before diving into the tutorials, you need a working Python environment with `uv`, LangGraph, and all required packages.
> **What you'll have at the end:** A fully configured project ready to run the tutorial examples from Sessions 01–15.

---

## Prerequisites

**Required:**
- Python 3.11 or 3.12 installed
- Basic familiarity with Python and command-line tools
- A terminal/shell (bash, zsh, or similar)

**Optional (for LLM-powered agents):**
- OpenAI API key (for Sessions 07, 10, and beyond)
- LangSmith account (for tracing and debugging)

---

## What is `uv`?

[`uv`](https://github.com/astral-sh/uv) is a fast Python package installer and resolver written in Rust. It's a drop-in replacement for `pip` and `pip-tools` that's significantly faster and more reliable for dependency management.

**Why we use it:**
- **Fast** — 10-100x faster than pip for installing packages
- **Reliable** — deterministic dependency resolution
- **Simple** — works like pip but better
- **Modern** — supports PEP 621 `pyproject.toml` natively

If you're familiar with `pip`, you already know 90% of `uv`. The main commands are:
- `uv pip install <package>` — install a package
- `uv pip sync requirements.txt` — install exact versions from a lockfile
- `uv venv` — create a virtual environment

---

## Step 1: Install `uv`

### macOS/Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Windows

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Verify installation

```bash
uv --version
```

You should see something like:

```
uv 0.4.x (or later)
```

---

## Step 2: Clone or create the project

### Option A: Start from scratch (recommended for learning)

Create a new directory and initialize the project structure:

```bash
mkdir agentic-world-simulator
cd agentic-world-simulator

# Create directory structure
mkdir -p src/{world,sensors,transport,bridge,agents/{cluster,supervisor},domains/wildfire,tools,resources}
mkdir -p tests examples docs/tutorial/content
```

### Option B: Clone the repository

If you have access to the repository:

```bash
git clone https://github.com/chrislomeli/agentic-world-simulator.git
cd agentic-world-simulator
```

---

## Step 3: Create `pyproject.toml`

This file defines your project metadata and dependencies. Create it in the project root:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "world-simulator"
version = "0.1.0"
description = "Event-driven world simulation engine with LangGraph agent runtime"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.11"
authors = [
    {name = "Your Name"}
]
keywords = ["langgraph", "agent", "simulation", "wildfire", "world-engine"]

dependencies = [
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "langgraph>=0.2",
    "langchain-core>=0.3",
]

[project.optional-dependencies]
llm = [
    "langchain-openai>=0.2",
]

[dependency-groups]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/sensors", "src/tools", "src/domains", "src/transport", "src/bridge", "src/world", "src/agents", "src/resources"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
asyncio_mode = "auto"
```

**Key dependencies explained:**

- **`pydantic`** — Data validation and settings management (used for all state models)
- **`pydantic-settings`** — Environment variable configuration
- **`langgraph`** — LangChain's graph-based agent framework (core of the agent runtime)
- **`langchain-core`** — LangChain primitives (tools, messages, runnables)
- **`langchain-openai`** — OpenAI LLM integration (optional, only needed for LLM-powered agents)

---

## Step 4: Create a virtual environment

```bash
uv venv
```

This creates a `.venv` directory with an isolated Python environment.

**Activate the virtual environment:**

**macOS/Linux:**
```bash
source .venv/bin/activate
```

**Windows:**
```powershell
.venv\Scripts\activate
```

You should see `(.venv)` in your terminal prompt.

---

## Step 5: Install dependencies

### Core dependencies (required for all sessions)

```bash
uv pip install -e .
```

This installs the project in editable mode with all core dependencies.

### LLM dependencies (optional, needed for Sessions 07, 10+)

```bash
uv pip install -e ".[llm]"
```

This adds `langchain-openai` for GPT-4 integration.

### Development dependencies (optional, for testing)

```bash
uv pip install --group dev
```

This adds `pytest`, `pytest-asyncio`, and `pytest-cov`.

---

## Step 6: Verify installation

Create a simple test script to verify everything works:

**`verify_setup.py`:**

```python
#!/usr/bin/env python3
"""Verify that all required packages are installed."""

import sys

def check_import(module_name, package_name=None):
    """Try to import a module and report success/failure."""
    package_name = package_name or module_name
    try:
        __import__(module_name)
        print(f"✓ {package_name} installed")
        return True
    except ImportError:
        print(f"✗ {package_name} NOT installed")
        return False

def main():
    print("Checking core dependencies...\n")
    
    checks = [
        ("pydantic", "pydantic"),
        ("pydantic_settings", "pydantic-settings"),
        ("langgraph", "langgraph"),
        ("langchain_core", "langchain-core"),
    ]
    
    all_ok = all(check_import(mod, pkg) for mod, pkg in checks)
    
    print("\nChecking optional dependencies...\n")
    
    optional_checks = [
        ("langchain_openai", "langchain-openai (for LLM agents)"),
        ("pytest", "pytest (for testing)"),
    ]
    
    for mod, pkg in optional_checks:
        check_import(mod, pkg)
    
    print("\n" + "="*50)
    if all_ok:
        print("✓ Core setup complete! Ready to start tutorials.")
        print("\nNext steps:")
        print("  1. Set OPENAI_API_KEY if using LLM agents")
        print("  2. Start with Session 01: World Engine and Grid")
        return 0
    else:
        print("✗ Setup incomplete. Install missing packages.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

Run it:

```bash
python verify_setup.py
```

Expected output:

```
Checking core dependencies...

✓ pydantic installed
✓ pydantic-settings installed
✓ langgraph installed
✓ langchain-core installed

Checking optional dependencies...

✓ langchain-openai (for LLM agents) installed
✓ pytest (for testing) installed

==================================================
✓ Core setup complete! Ready to start tutorials.

Next steps:
  1. Set OPENAI_API_KEY if using LLM agents
  2. Start with Session 01: World Engine and Grid
```

---

## Step 7: Configure environment variables (for LLM sessions)

**When you need this:** Sessions 07, 10, and beyond use LLM-powered agents. Sessions 01–06 work without any API keys (they use stub/deterministic agents).

LangChain automatically reads API keys from environment variables. You have two options:

### Option A: Export in your shell (simple, temporary)

```bash
export OPENAI_API_KEY=sk-...
```

This works for the current terminal session only. You'll need to re-export if you close the terminal.

### Option B: Use a `.env` file (persistent, recommended)

Create a `.env` file in the project root:

```bash
# OpenAI API key (required for LLM agents in Sessions 07+)
OPENAI_API_KEY=sk-...

# LangSmith tracing (optional, for debugging)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_...
LANGCHAIN_PROJECT=wildfire-simulation
```

**Important:** Add `.env` to your `.gitignore` to avoid committing secrets:

```bash
echo ".env" >> .gitignore
```

LangChain will automatically load these variables when you import `langchain_openai` or other LangChain modules.

---

## Step 8: Verify API key setup (for LLM sessions)

Before running LLM-powered sessions, verify your API key is accessible:

**`verify_api_key.py`:**

```python
#!/usr/bin/env python3
"""Verify that OpenAI API key is set and valid."""

import os
import sys

def check_api_key():
    """Check if OPENAI_API_KEY is set in environment."""
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        print("✗ OPENAI_API_KEY not set")
        print("\nTo fix this, either:")
        print("  1. Export in your shell:")
        print("     export OPENAI_API_KEY=sk-...")
        print("  2. Create a .env file with:")
        print("     OPENAI_API_KEY=sk-...")
        return False
    
    if not api_key.startswith("sk-"):
        print(f"✗ OPENAI_API_KEY looks invalid (doesn't start with 'sk-')")
        print(f"   Current value: {api_key[:10]}...")
        return False
    
    print(f"✓ OPENAI_API_KEY is set ({api_key[:10]}...)")
    
    # Optional: test the key with a simple API call
    try:
        from langchain_openai import ChatOpenAI
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        response = llm.invoke("Say 'API key works'")
        print(f"✓ API key verified (test call successful)")
        print(f"  Response: {response.content}")
        return True
    except ImportError:
        print("ℹ langchain-openai not installed (run: uv pip install -e '.[llm]')")
        print("  Skipping API validation test")
        return True
    except Exception as e:
        print(f"✗ API key test failed: {e}")
        print("  Your key might be invalid or expired")
        return False

def check_langsmith():
    """Check if LangSmith tracing is configured (optional)."""
    tracing = os.getenv("LANGCHAIN_TRACING_V2")
    api_key = os.getenv("LANGCHAIN_API_KEY")
    
    if tracing and api_key:
        print(f"✓ LangSmith tracing enabled")
        print(f"  Project: {os.getenv('LANGCHAIN_PROJECT', 'default')}")
    else:
        print("ℹ LangSmith tracing not configured (optional)")

def main():
    print("Checking API key configuration...\n")
    
    api_ok = check_api_key()
    print()
    check_langsmith()
    
    print("\n" + "="*50)
    if api_ok:
        print("✓ Ready for LLM-powered sessions!")
        return 0
    else:
        print("✗ Fix API key issues before running LLM sessions")
        print("  (Sessions 01-06 work without API keys)")
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

Run it:

```bash
python verify_api_key.py
```

**Expected output (if configured):**

```
Checking API key configuration...

✓ OPENAI_API_KEY is set (sk-proj-ab...)
✓ API key verified (test call successful)
  Response: API key works

ℹ LangSmith tracing not configured (optional)

==================================================
✓ Ready for LLM-powered sessions!
```

**Expected output (if not configured):**

```
Checking API key configuration...

✗ OPENAI_API_KEY not set

To fix this, either:
  1. Export in your shell:
     export OPENAI_API_KEY=sk-...
  2. Create a .env file with:
     OPENAI_API_KEY=sk-...

ℹ LangSmith tracing not configured (optional)

==================================================
✗ Fix API key issues before running LLM sessions
  (Sessions 01-06 work without API keys)
```

---

## Step 9: Create initial project structure

Create placeholder `__init__.py` files to make directories importable:

```bash
# Core modules
touch src/__init__.py
touch src/world/__init__.py
touch src/sensors/__init__.py
touch src/transport/__init__.py
touch src/bridge/__init__.py
touch src/agents/__init__.py
touch src/agents/cluster/__init__.py
touch src/agents/supervisor/__init__.py
touch src/domains/__init__.py
touch src/domains/wildfire/__init__.py
touch src/tools/__init__.py
touch src/resources/__init__.py

# Tests
touch tests/__init__.py
```

**Verify imports work:**

```python
python -c "import world; import sensors; import agents; print('✓ All modules importable')"
```

---

## Common Issues

### Issue: `uv: command not found`

**Solution:** Make sure `uv` is in your PATH. Try closing and reopening your terminal, or run:

```bash
source ~/.bashrc  # or ~/.zshrc on macOS
```

### Issue: `ModuleNotFoundError: No module named 'pydantic'`

**Solution:** Make sure your virtual environment is activated:

```bash
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows
```

Then reinstall:

```bash
uv pip install -e .
```

### Issue: `ImportError: cannot import name 'BaseModel' from 'pydantic'`

**Solution:** You might have an old version of Pydantic. Upgrade:

```bash
uv pip install --upgrade pydantic
```

### Issue: LangGraph version conflicts

**Solution:** Make sure you have compatible versions:

```bash
uv pip install --upgrade langgraph langchain-core
```

---

## What you've built

At this point you have:

✅ **`uv` installed** — fast, modern Python package manager  
✅ **Virtual environment** — isolated Python environment in `.venv`  
✅ **Core dependencies** — Pydantic, LangGraph, LangChain  
✅ **Project structure** — organized `src/` directory with modules  
✅ **Verified setup** — all imports working  
✅ **Optional: LLM integration** — OpenAI API key configured  
✅ **Optional: Development tools** — pytest for testing  

You're ready to start building! Head to **Session 01: World Engine and Grid** to begin.

---

## Quick reference: Common `uv` commands

```bash
# Create virtual environment
uv venv

# Install package
uv pip install <package>

# Install from pyproject.toml
uv pip install -e .

# Install with optional dependencies
uv pip install -e ".[llm]"

# Install development dependencies
uv pip install --group dev

# Upgrade all packages
uv pip install --upgrade -e .

# List installed packages
uv pip list

# Freeze dependencies to requirements.txt
uv pip freeze > requirements.txt

# Install from requirements.txt
uv pip sync requirements.txt
```

---

*Next: Session 01 — World Engine and Grid. You'll build the foundation: a grid-based world with fire spread physics.*
