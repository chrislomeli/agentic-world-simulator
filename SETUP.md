# Symbolic Music Project Setup

## Quick Start

### 1. Start Memgraph Database
```bash
docker-compose up -d
```

### 2. Install the Package
```bash
pip install -e .
```

### 3. Apply Graph Schema (run once per fresh DB)
```bash
python -c "from symbolic_music.persistence.schema import setup_schema; setup_schema()"
```

### 4. Load the Demo Composition
```bash
cd examples
python demo_twinkle_multipart.py
```

### 5. Render from Graph to music21
```bash
python demo_render_from_graph.py
```

## Access Points

- **Memgraph Lab (Web UI)**: http://localhost:7444
- **Database connection**: bolt://localhost:7687

## Development Workflow

1. **Start Memgraph**: `docker-compose up -d`
2. **Install package**: `pip install -e .`
3. **Apply schema**: `python -c "from symbolic_music.persistence.schema import setup_schema; setup_schema()"`
4. **Load demo**: `cd examples && python demo_twinkle_multipart.py`
5. **Explore data**: Open http://localhost:7444
6. **Run tests**: `pytest tests/`
7. **Stop services**: `docker-compose down`

## Project Architecture

```
src/symbolic_music/
├── domain/           # Pure domain models
├── persistence/      # Graph database (writer, reader, adapter, schema)
└── rendering/        # Output formats (music21)

examples/             # Demo scripts
tests/                # Unit tests
```

### Usage
```python
from symbolic_music.domain import CompositionSpec, NoteEvent, Pitch
from symbolic_music.persistence import GraphMusicWriter, GraphMusicReader
from symbolic_music.rendering import render_composition
```

Legacy code in `source/` and `source_json/` kept for reference.

## Data Persistence

- Data automatically saved to Docker volume `mg_data`
- Survives container restarts
- For backup: `docker exec memgraph mg_dump > backup.sql`
