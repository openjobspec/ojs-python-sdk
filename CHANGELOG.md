# Changelog

All notable changes to the OpenJobSpec Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.0](https://github.com/openjobspec/ojs-python-sdk/compare/v0.3.0...v0.4.0) (2026-04-20)


### Features

* add asyncio-native worker context manager ([3102dc3](https://github.com/openjobspec/ojs-python-sdk/commit/3102dc3b7b68f1d0ce886061fdd258bb687356b1))
* add asyncio-native worker with uvloop support ([ff1cd5b](https://github.com/openjobspec/ojs-python-sdk/commit/ff1cd5b36fcdaf25925a0f2ff6e4d3d88cc069b6))
* add graceful shutdown signal handler ([2fa8065](https://github.com/openjobspec/ojs-python-sdk/commit/2fa8065a0cd25cf48149730e54bd65b6582f9d72))
* add initial project structure ([8ad8ab4](https://github.com/openjobspec/ojs-python-sdk/commit/8ad8ab47195d316c20c961eecdcf53716a2c60e7))
* add initial project structure ([21752dc](https://github.com/openjobspec/ojs-python-sdk/commit/21752dc7cb78043af8fd590d03147d59b09378f0))
* add retry backoff configuration ([12ceee3](https://github.com/openjobspec/ojs-python-sdk/commit/12ceee3f628a76a1f3d57a9a95170e816c70378b))
* add retry backoff configuration ([e426f3f](https://github.com/openjobspec/ojs-python-sdk/commit/e426f3fc9a4180eb083953b3a853769e7df4ddcd))
* add workflow chain primitive ([46da197](https://github.com/openjobspec/ojs-python-sdk/commit/46da1977d54e0ef1c422dc76ebd1695a36bc0b5e))
* expose batch enqueue endpoint ([1e75abd](https://github.com/openjobspec/ojs-python-sdk/commit/1e75abd974386e3d8bff6fd208c9927e05b7abf8))
* implement core handler interfaces ([3b5e3d2](https://github.com/openjobspec/ojs-python-sdk/commit/3b5e3d29026da1b4419eff9260d174c082d056f4))
* implement core handler interfaces ([1abc1e2](https://github.com/openjobspec/ojs-python-sdk/commit/1abc1e21c5dbb6bdbbe036fc2af11d374760191e))
* improve HTTP transport efficiency and worker polling ([5cd4f6a](https://github.com/openjobspec/ojs-python-sdk/commit/5cd4f6ae9710199f4026533ee41900c3eeb3c041))


### Bug Fixes

* correct job state transition guard ([b424134](https://github.com/openjobspec/ojs-python-sdk/commit/b4241346fcde019e1d111888e9f8241971e22f8b))
* correct timestamp serialization ([4e70cb2](https://github.com/openjobspec/ojs-python-sdk/commit/4e70cb29b5acdc8c48e951733428960af871b83c))
* correct timestamp serialization ([4efc96f](https://github.com/openjobspec/ojs-python-sdk/commit/4efc96f47512c6c65d773241315e0389f8a5f011))
* handle nil pointer in middleware chain ([37ce2b0](https://github.com/openjobspec/ojs-python-sdk/commit/37ce2b0948541addbdb1a50b17f55e2318491638))
* handle nil pointer in middleware chain ([36c353c](https://github.com/openjobspec/ojs-python-sdk/commit/36c353c39bb5b85982e095d9a693fffa075032d7))
* improve HTTP transport reliability ([2d46cd5](https://github.com/openjobspec/ojs-python-sdk/commit/2d46cd5d7fcc226cc542a3bbafccae40d651211f))
* prevent double-close on worker pool ([43429aa](https://github.com/openjobspec/ojs-python-sdk/commit/43429aa5a84021782270020ddaff3454ec7426c5))
* resolve edge case in input validation ([f930c4f](https://github.com/openjobspec/ojs-python-sdk/commit/f930c4f0827d62084b51a5e0a33d8c5b5e13ee88))
* resolve edge case in input validation ([a6348f1](https://github.com/openjobspec/ojs-python-sdk/commit/a6348f1d6c34448009cec36d198db5282c70e08d))


### Performance Improvements

* cache compiled regex patterns ([6fd49d2](https://github.com/openjobspec/ojs-python-sdk/commit/6fd49d2508ebc422aab489600f8a0b936661c81a))
* optimize data processing loop ([83aae00](https://github.com/openjobspec/ojs-python-sdk/commit/83aae0036f88499886d87c54ac683db590bbcbb2))
* optimize data processing loop ([82ea95d](https://github.com/openjobspec/ojs-python-sdk/commit/82ea95db78c48d61d5d0aa9916512832c5adc9be))
* reduce allocations in hot path ([fcd6d11](https://github.com/openjobspec/ojs-python-sdk/commit/fcd6d11ed0c5cba7d4f67544b53f8e1d9c02a3a6))


### Documentation

* add API reference section ([1e4b19b](https://github.com/openjobspec/ojs-python-sdk/commit/1e4b19b02c876ef59702698ff837398a4274da1d))
* add API reference section ([d12448b](https://github.com/openjobspec/ojs-python-sdk/commit/d12448b876411fd78f84d7ddc6c648b56c5152a7))
* add contributing guidelines ([1f97ef0](https://github.com/openjobspec/ojs-python-sdk/commit/1f97ef02ad1d85fc9413d326e59d02b8bcfd9e7d))
* document extension points ([28b922d](https://github.com/openjobspec/ojs-python-sdk/commit/28b922d4d42241f9fa8ccd67d5ab84e2d1e24a12))
* document extension points ([854d781](https://github.com/openjobspec/ojs-python-sdk/commit/854d7815c773e1344717262dcb65e9262c8d00c8))
* update quickstart example ([cce026d](https://github.com/openjobspec/ojs-python-sdk/commit/cce026d159063e24d70ca4888957a189b819199d))
* update README with usage instructions ([05552ee](https://github.com/openjobspec/ojs-python-sdk/commit/05552ee56cff4e3708d2b8447239369733f422a9))
* update README with usage instructions ([c8e09ed](https://github.com/openjobspec/ojs-python-sdk/commit/c8e09ed4c5c5f3b56f82f08667e93938a3f492e6))

## [Unreleased]

## [0.4.0] - 2026-04-20

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
