.PHONY: install test lint typecheck check clean coverage

install:
	pip install -e ".[dev]"

test:
	pytest

coverage:
	pytest --cov=ojs --cov-report=term-missing --cov-report=xml

lint:
	ruff check .

typecheck:
	mypy src/

check: lint typecheck test

clean:
	rm -rf dist/ build/ *.egg-info src/*.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
