.PHONY: install test lint format typecheck check clean coverage docs benchmark

install:
	uv sync --locked --python 3.11 --all-extras --dev

test:
	uv run pytest

coverage:
	uv run pytest --cov=ojs --cov-report=term-missing --cov-report=xml

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy src/

check: lint typecheck test

benchmark:
	uv run pytest tests/test_benchmarks.py --benchmark-only

docs:
	uv run sphinx-build -W -b html docs docs/_build/html

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml docs/_build
	find . -type d -name __pycache__ -exec rm -rf {} +
