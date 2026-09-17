# Contributing

## Development setup

Use Python 3.12 or newer and install the development dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Checks

Run the full test and lint suites before submitting a change:

```bash
pytest
ruff check .
```

Scraper changes should include a representative fixture and parser test. Keep
live network access out of unit tests so the suite remains deterministic.
