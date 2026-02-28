# Changelog

All notable changes to the OpenJobSpec Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0](https://github.com/openjobspec/ojs-python-sdk/compare/v0.1.0...v0.2.0) (2026-02-28)


### Features

* add configurable request timeout option ([80f5a07](https://github.com/openjobspec/ojs-python-sdk/commit/80f5a07d37a3d9fc692ce7fa01cf56dae433ba3b))
* add durable execution module for Python SDK ([af0beaa](https://github.com/openjobspec/ojs-python-sdk/commit/af0beaa15c4c49b937b27338f285dce1d5ef1e5c))
* implement exponential backoff for retries ([8f93841](https://github.com/openjobspec/ojs-python-sdk/commit/8f938416e2bf2966bf2e17d42e388a221736e19d))


### Bug Fixes

* correct asyncio task cancellation handling ([9bb4067](https://github.com/openjobspec/ojs-python-sdk/commit/9bb4067fd66b6012fe38589fb1797123fcf90000))
* correct error handling in graceful shutdown ([4e33914](https://github.com/openjobspec/ojs-python-sdk/commit/4e339149cfed75083e643572caa851e5d55118ab))
* handle empty response body gracefully ([113fbb7](https://github.com/openjobspec/ojs-python-sdk/commit/113fbb7c7af9dca299e9ddd9afb72e8fff031a95))

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
