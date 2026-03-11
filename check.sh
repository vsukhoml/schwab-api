#!/bin/bash
set -e

echo "Running black..."
.venv/bin/black schwab_api/ tests/ portfolio.py

echo "Running isort..."
.venv/bin/isort schwab_api/ tests/ portfolio.py

echo "Running mypy..."
.venv/bin/mypy --ignore-missing-imports schwab_api/

echo "Running unit tests..."
PYTHONPATH=. .venv/bin/python -m unittest discover tests

echo "All checks passed successfully!"
