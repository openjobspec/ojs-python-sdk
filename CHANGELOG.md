# Changelog

All notable changes to the OpenJobSpec Python SDK will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-09-02

### Added

- `Client` and `SyncClient` now expose the normative worker `fetch`, `ack`,
  and `nack` operations for integrations that act as protocol consumers.

### Changed

- `cryptography` is now an unconditional dependency because the package
  imports encryption support from its public package facade.

### Fixed

- Serverless completion callbacks (`LambdaHandler`, `AzureFunctionsHandler`)
  now send `Authorization: Bearer <api_key>` instead of a bespoke
  `X-OJS-API-Key` header, matching the OJS HTTP binding's authentication
  convention; a new optional `headers` parameter is merged additively
  alongside it.
- Azure `handle_queue_message` now redelivers (raises, preserving the
  original error as the cause) only for retryable handler failures, even
  after a successful NACK callback, and completes the message for
  non-retryable outcomes (invalid input, unknown job type, or an
  unserializable result) instead of retrying a poison message forever.
- Azure `handle_http_request` now classifies a malformed JSON body as
  `invalid_request` (HTTP 400, non-retryable) before invoking the handler,
  instead of surfacing it as an opaque, retryable `handler_error`.
- The gRPC job projection no longer coerces an explicit
  `retry.max_attempts = 0`, `retry.backoff_coefficient = 0.0`, or top-level
  `max_attempts = 0` into the SDK's nonzero defaults.
- `rpc_error_mapper` no longer lets a malformed `grpc-status-details-bin`
  trailer crash with a raw protobuf `DecodeError`; it now falls back to the
  ordinary gRPC status-code mapping.
- `Client.enqueue_batch()` now resolves each item's middleware terminal
  with the real transport-returned `Job`, so post-`next()` observation and
  return-value transformations by enqueue middleware are honored instead
  of being silently discarded.
- The SSE client now distinguishes an absent `id` field (inherits the
  previous event's id) from an explicit empty `id` (resets it), and a
  reconnect correctly omits `Last-Event-ID` after such a reset.
- The SSE client now treats an HTTP `204 No Content` response as a
  terminal "stop reconnecting" signal, per the SSE specification, instead
  of reconnecting as if it were an ordinary empty stream.
- `Worker` shutdown (via an OS signal, an explicit `stop()` call, or a
  server "terminate" heartbeat directive) now atomically publishes
  `WorkerState.TERMINATE` before requesting the shutdown/drain, and a
  "quiet"/"running" heartbeat directive already in flight can no longer
  overwrite `TERMINATE` after shutdown has been requested.

## [0.4.1] - 2026-04-21

### Fixed

- Suppressed cleanup exceptions are now surfaced through debug logging.

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

[Unreleased]: https://github.com/openjobspec/ojs-python-sdk/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/openjobspec/ojs-python-sdk/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/openjobspec/ojs-python-sdk/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/openjobspec/ojs-python-sdk/compare/v0.1.0...v0.4.0
[0.1.0]: https://github.com/openjobspec/ojs-python-sdk/releases/tag/v0.1.0
