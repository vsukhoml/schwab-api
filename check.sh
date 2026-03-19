#!/bin/bash
set -e

echo "Running ruff format..."
.venv/bin/ruff format schwab_api/ tests/

echo "Running ruff check..."
.venv/bin/ruff check --fix schwab_api/ tests/

echo "Running mypy..."
.venv/bin/mypy --ignore-missing-imports schwab_api/

echo "Running unit tests..."
PYTHONPATH=. .venv/bin/python -m unittest discover tests

echo "All checks passed successfully!"
