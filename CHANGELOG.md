# Changelog

All notable changes to the OpenJobSpec Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2025-02-12

### Added

- Async-first `Client` for enqueuing jobs, batch operations, and queue management.
- `SyncClient` wrapper for non-async usage.
- `Worker` with `asyncio.TaskGroup`-based structured concurrency.
- Handler registration via `@worker.register("job.type")` decorator.
- Enqueue and execution middleware chains with `next()` pattern.
- `RetryPolicy` with exponential backoff, jitter, and ISO 8601 duration support.
- Workflow primitives: `chain()`, `group()`, `batch()`.
- `WorkerState` enum for type-safe worker lifecycle states.
- Full 8-state `JobState` enum matching the OJS specification.
- `UniquePolicy` for job deduplication.
- `Event` and `EventType` for OJS event definitions.
- `Queue` and `QueueStats` types for queue introspection.
- Abstract `Transport` interface with `HTTPTransport` implementation using httpx.
- Structured error hierarchy: `OJSError`, `OJSAPIError`, `DuplicateJobError`, `JobNotFoundError`, `QueuePausedError`, `RateLimitedError`.
- Graceful shutdown with SIGTERM/SIGINT handling and configurable grace period.
- Heartbeat loop with server-initiated state transitions (quiet, terminate).
- PEP 561 `py.typed` marker for downstream type checking.

[Unreleased]: https://github.com/openjobspec/ojs-python-sdk/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/openjobspec/ojs-python-sdk/releases/tag/v0.1.0
