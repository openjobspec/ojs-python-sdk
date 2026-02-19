# Changelog

All notable changes to the OpenJobSpec Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.1.0 (2026-02-19)


### Features

* **client:** add async/sync client for job enqueue and management ([3b8695d](https://github.com/openjobspec/ojs-python-sdk/commit/3b8695d5c528bdc34d4bdc916c32763d24e12a65))
* **client:** add manifest, dead-letter, cron, and schema operations ([5a9292a](https://github.com/openjobspec/ojs-python-sdk/commit/5a9292a6415c2dac37fdecc53b77f5f5e852836d))
* **client:** complete SyncClient API surface ([cae094e](https://github.com/openjobspec/ojs-python-sdk/commit/cae094e9ef42cde1c280b08c6d258d3c5475015d))
* **core:** add error types and retry policy with ISO 8601 support ([616871e](https://github.com/openjobspec/ojs-python-sdk/commit/616871e36a22339a35b983de2183c117c5ed417d))
* **core:** add job model, queue types, and event definitions ([27f0407](https://github.com/openjobspec/ojs-python-sdk/commit/27f0407967e0674e13a20325463dcf4eefd56373))
* **core:** add middleware chains for enqueue and execution ([8dbb07f](https://github.com/openjobspec/ojs-python-sdk/commit/8dbb07f85c56c7155b9ee7bf97f0868681a1d488))
* **core:** add workflow primitives (chain, group, batch) ([b8676fe](https://github.com/openjobspec/ojs-python-sdk/commit/b8676feba3d7498dc680311295049f648f3c1625))
* **errors:** add RateLimitInfo for structured rate-limit headers ([d212990](https://github.com/openjobspec/ojs-python-sdk/commit/d212990b5309e89c6f955e598e2ad2cb95845ce6))
* **middleware:** add built-in middleware implementations ([90413a5](https://github.com/openjobspec/ojs-python-sdk/commit/90413a56928b237779151d27a833ada4334c3c02))
* **ml:** add ML/AI resource extension module ([ff9ec2e](https://github.com/openjobspec/ojs-python-sdk/commit/ff9ec2e6a6a4c8fd97f574729a823ef583226554))
* **otel:** add OpenTelemetry middleware for job instrumentation ([354ce7c](https://github.com/openjobspec/ojs-python-sdk/commit/354ce7cf3864acc2d684116a4bcb8704a8dd3402))
* **progress:** add job progress reporting module ([f0ec326](https://github.com/openjobspec/ojs-python-sdk/commit/f0ec326b31eb5bbd4e17aba607b65cde9077c612))
* **testing:** add fake mode and test assertion utilities ([f571632](https://github.com/openjobspec/ojs-python-sdk/commit/f57163293106aca23909398c6b9039312de365b9))
* **testing:** wire fake_mode to Client enqueue methods ([13337d5](https://github.com/openjobspec/ojs-python-sdk/commit/13337d56749b5ed0101de59c99e4c7098c0bc306))
* **transport:** add abstract transport layer and HTTP binding ([d8536f1](https://github.com/openjobspec/ojs-python-sdk/commit/d8536f1b42d69fc490b98bcf47139b2ceb1f38d6))
* **transport:** add manifest, dead-letter, cron, and schema endpoints ([f4ae8af](https://github.com/openjobspec/ojs-python-sdk/commit/f4ae8af272e1984b185d670fa90dbc5d8d0e8d4a))
* **transport:** add progress reporting endpoint to transport layer ([19ae7b5](https://github.com/openjobspec/ojs-python-sdk/commit/19ae7b591ee352052f3618f85bc010ba75f70f80))
* **worker:** add async worker with TaskGroup concurrency ([d0e2a06](https://github.com/openjobspec/ojs-python-sdk/commit/d0e2a06ee42615305ab57ef00cbd90ab1a2300b1))
* **worker:** warn when starting with no registered handlers ([e8f74dc](https://github.com/openjobspec/ojs-python-sdk/commit/e8f74dcce3088a50f45d4532cd9cd38b3246f0eb))


### Bug Fixes

* **client:** rename type param to job_type to avoid shadowing builtin ([8cd7e4d](https://github.com/openjobspec/ojs-python-sdk/commit/8cd7e4dc488f1c08e68a3fd9399612da60499c3a))
* **client:** replace assert with proper OJSError raise ([7cd2667](https://github.com/openjobspec/ojs-python-sdk/commit/7cd2667e93b5b097860aeaa83a575772bc2888f5))
* **lint:** resolve all ruff violations and update lint config ([f4873d5](https://github.com/openjobspec/ojs-python-sdk/commit/f4873d5a28e959c078fb6ef122cbd98d27c035ce))
* **middleware:** add noqa for intentional builtin shadowing ([265dc65](https://github.com/openjobspec/ojs-python-sdk/commit/265dc65e95ab27c0c31512a8e05eb85deed2de36))
* **transport:** remove dead code and fix return type annotation ([0c0e9a2](https://github.com/openjobspec/ojs-python-sdk/commit/0c0e9a254bf951aa9800f0b76cf9653687a65a15))
* **types:** add explicit type annotations for dict and Callable ([4df5405](https://github.com/openjobspec/ojs-python-sdk/commit/4df5405c8e098e07a3ee385b46bc52766419384d))
* **worker:** prevent semaphore leak on transport fetch errors ([8d9d003](https://github.com/openjobspec/ojs-python-sdk/commit/8d9d003218c12b01228fd36403b203a5d08e4259))
* **worker:** replace assert with raise and add WorkerState enum ([603ce01](https://github.com/openjobspec/ojs-python-sdk/commit/603ce015d0544bb530b504118899e804f2ec7fdb))


### Documentation

* add Code of Conduct ([8e85b3c](https://github.com/openjobspec/ojs-python-sdk/commit/8e85b3ca942d12fcaf556a23b84240b1882313cb))
* add Sphinx documentation scaffolding ([0d46e8d](https://github.com/openjobspec/ojs-python-sdk/commit/0d46e8d615c3d30c597981e730347383e3c4d28f))
* add usage examples and README ([7a362d6](https://github.com/openjobspec/ojs-python-sdk/commit/7a362d6fedff21f425a1fcbc3657b05ceae4bd0c))
* **examples:** add middleware usage example ([f6a05eb](https://github.com/openjobspec/ojs-python-sdk/commit/f6a05ebb5be9b5af36ac503f951e1ef0c737d76d))
* **readme:** add Resources section with project links ([8d68900](https://github.com/openjobspec/ojs-python-sdk/commit/8d689003045fa88e972a5f7914eee3ed2bfc2640))
* **security:** add security policy ([8cd0bd5](https://github.com/openjobspec/ojs-python-sdk/commit/8cd0bd52f6f4bd075ecd27d3d7c8b85b2cf035bc))

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
