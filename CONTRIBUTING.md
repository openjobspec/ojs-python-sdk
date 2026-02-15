# Contributing to the OJS Python SDK

Thank you for your interest in contributing to the OpenJobSpec Python SDK!

## Development Setup

```bash
# Clone the repository
git clone https://github.com/openjobspec/ojs-python-sdk.git
cd ojs-python-sdk

# Create a virtual environment (Python 3.11+ required)
python3.12 -m venv .venv
source .venv/bin/activate

# Install with dev dependencies
pip install -e ".[dev]"
```

## Running Checks

```bash
# Run all checks (lint, typecheck, test)
make check

# Run individually
make lint        # ruff check .
make typecheck   # mypy src/
make test        # pytest
make coverage    # pytest with coverage report
```

## Code Style

- **Formatting**: [Ruff](https://docs.astral.sh/ruff/) for linting (100-char line limit)
- **Type hints**: Complete type annotations on all public APIs; `mypy --strict`
- **Docstrings**: Google-style docstrings on public classes and methods
- **Imports**: Use `from __future__ import annotations` in all modules

## Pull Request Process

1. Fork the repository and create a feature branch from `main`
2. Make your changes with clear, focused commits
3. Ensure all checks pass: `make check`
4. Update `CHANGELOG.md` under `[Unreleased]` if the change is user-facing
5. Open a pull request with a clear description of the change

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(client): add support for job priorities
fix(worker): prevent semaphore leak on fetch errors
docs: update README quick start example
test(retry): add edge case for max interval cap
chore: update ruff to 0.5
```

## Testing

- Write tests for all new functionality
- Use `FakeTransport` from `tests/conftest.py` for client/worker tests
- Use `pytest-httpx` for HTTP transport tests
- Integration tests go in `tests/integration/` and are gated behind `OJS_INTEGRATION_TESTS=1`

## Architecture Overview

```
src/ojs/
├── __init__.py          # Public API exports
├── _utils.py            # Shared internal utilities
├── client.py            # Client (producer) and SyncClient
├── errors.py            # Exception hierarchy
├── events.py            # Event types (CloudEvents-inspired)
├── job.py               # Job, JobRequest, JobContext, JobState
├── middleware.py         # Enqueue and execution middleware chains
├── otel.py              # OpenTelemetry middleware (optional)
├── queue.py             # Queue and QueueStats types
├── retry.py             # RetryPolicy with ISO 8601 durations
├── testing.py           # Fake mode and test assertions
├── transport/
│   ├── base.py          # Abstract Transport interface
│   └── http.py          # HTTPTransport (httpx-based)
├── worker.py            # Worker (consumer) with structured concurrency
└── workflow.py          # Workflow builders: chain(), group(), batch()
```

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
