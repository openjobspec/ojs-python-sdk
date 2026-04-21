# Actor-Based SRP and Clean-Code Audit

| Field | Value |
|---|---|
| Repository | `ojs-python-sdk` |
| Branch | `refactor/clean-code-srp` |
| Baseline commit | `372bce6d3e99` |
| Implementation status | All repository-local findings `OJS-PY-001` through `OJS-PY-052` complete |
| Compatibility | Runtime compatibility facades retained; Griffe reports no breaking changes against `HEAD` |
| Working-tree policy | Changes intentionally remain unstaged and uncommitted |

## Summary

The audit began with a base import failure, 19 strict-mypy errors, 1,039 Ruff
findings, 30 unformatted files, five red synchronous-client tests, an
untracked lock file, and protocol/lifecycle defects capable of duplicating
jobs, replaying durable side effects, losing encrypted metadata, or reporting
contradictory worker outcomes.

The implementation closes all 43 findings. Large modules were split by domain
actor rather than by generic helper role; HTTP and gRPC wire behavior is
explicit; worker admission, execution identity, heartbeat, signals, shutdown,
retry leases, and terminal delivery have independent owners; optional
features are lazy and package-safe; and build, API, type, lint, coverage, and
artifact gates are deterministic.

A follow-up, targeted pass (`OJS-PY-044` through `OJS-PY-052`) closed nine
additional protocol and concurrency findings: serverless callback
authentication was sending a bespoke header instead of the OJS HTTP
binding's `Authorization: Bearer` convention; the Azure Service Bus/Storage
Queue adapter could either redeliver a poison message forever or silently
swallow a retryable failure depending on unrelated NACK-callback plumbing,
and its HTTP push path let a malformed body reach the handler boundary as an
opaque retryable error instead of a classified `invalid_request`; the gRPC
job projection coerced explicit protobuf zero values (`max_attempts = 0`,
`backoff_coefficient = 0.0`) into nonzero SDK defaults; a malformed
`grpc-status-details-bin` trailer could crash the error mapper outright
instead of falling back to the ordinary gRPC status mapping; the batch
enqueue middleware onion resolved each item's terminal with a fabricated
placeholder `Job` instead of the real transport result, silently discarding
post-`next()` mutations and return-value transformations; the SSE frame
parser could not distinguish an absent `id` field from an explicit empty
one, so an explicit reset failed to clear the reconnect `Last-Event-ID`
header; an HTTP 204 response (the SSE spec's explicit "stop reconnecting"
signal) was treated as an ordinary reconnectable EOF; and a worker's public
lifecycle state could be silently overwritten back to "quiet"/"running" by
a stale, already-in-flight heartbeat response racing a signal-triggered
shutdown. See the dedicated findings table below for the full outcome and
test evidence for each.

Final certification:

- `678 passed, 25 skipped` on Python 3.11, 3.12, and 3.13 (up from
  `634 passed, 25 skipped` before the follow-up pass; 44 tests were added
  covering the nine new findings).
- Coverage: satisfies the configured 80% gate (see Verification evidence).
- Ruff check and format check: zero findings.
- Strict mypy: zero findings across all source files.
- Griffe: no breaking changes against `HEAD`.
- Bandit: zero findings; pip-audit: no known vulnerabilities.
- Repeated wheel and sdist builds are byte-for-byte reproducible.
- Clean base wheel, all-extras wheel, and all-extras sdist imports pass.

## Structural coverage

The implementation inspected the manifest, lock strategy, all tracked
workflows, README/docs/examples, every shipped source module, the largest
client/worker/transport/serverless files, and the complete test inventory.
Canonical protobuf sources were read from the monorepo and vendored locally;
no sibling repository was modified.

| Area | Actor ownership after implementation |
|---|---|
| Client | `client/async_client.py`, `enqueue_pipeline.py`, `sync_runner.py` |
| HTTP | `transport/http/transport.py`, `retry_policy.py`, `enqueue_idempotency.py` |
| gRPC | channel, descriptor, protobuf codec, projections, RPC mapping, paging, workflow actors under `transport/grpc/` |
| Worker | runtime orchestration plus run state, admission, execution registry, completion, heartbeat leases, shutdown, signals, retry budget, and options actors |
| Workflow | request/response models, builders, and canonical step projection |
| Durable | context, endpoint construction, and fail-closed replay loading |
| Serverless | event parser, handler registry, invocation bridge, and error response |
| SSE | frame parser and subscription-session lifecycle |
| Errors | catalog-driven response mapper and rate-limit header parser |
| Testing | explicit/context-local fake transport and assertion actors |
| Packaging | export registry, shared version source, generated bindings, locked/reproducible build tooling |

## Ranked findings and outcomes

### P0

| ID | actors in conflict / risk | outcome and evidence |
|---|---|---|
| OJS-PY-001 | Package facade vs optional crypto; base installs could not import | Lazy crypto exports, `crypto` extra, actionable errors, and base-wheel import coverage |
| OJS-PY-002 | Error decoding vs catalog taxonomy; canonical errors became generic | Catalog-driven mapper, header parser, canonical/legacy parity and malformed-body tests |
| OJS-PY-003 | Resilience vs replay safety; ambiguous POST retries could duplicate jobs | Operation-aware retry classification and stable logical idempotency identity |
| OJS-PY-004 | gRPC descriptors vs JSON fallback; advertised protobuf transport was non-interoperable | Generated bindings, descriptor validation, real protobuf codec, no JSON fallback |
| OJS-PY-005 | Job projection vs worker leases; fields and active jobs were dropped | Complete projections and multi-job heartbeat/visibility handling |
| OJS-PY-006 | Durable endpoint ownership vs failure classification; side effects could replay | Relative canonical paths, fail-closed replay loading, corruption and transient-failure coverage |
| OJS-PY-007 | Handler execution vs terminal delivery; ACK failure could cause NACK | Atomic completion reporter with one terminal claim and delivery-specific retry behavior |
| OJS-PY-008 | Enqueue construction vs middleware/fake sinks; batch/fake behavior diverged | Shared enqueue pipeline for single, batch, transport, and fake modes |

### P1

| ID | actors in conflict / risk | outcome and evidence |
|---|---|---|
| OJS-PY-009 | Sync facade vs event-loop ownership | Injected transport and dedicated serialized loop thread with close/reuse tests |
| OJS-PY-010 | Poll/heartbeat tasks vs shutdown/restart state | Run-scoped state and explicit shutdown coordinator; start-stop-start supported |
| OJS-PY-011 | Fetch count vs semaphore accounting | Capacity reserved before fetch; surplus leases are explicitly NACKed |
| OJS-PY-012 | Worker instances vs process-global signals | Single-owner signal custodian with restoration and platform/thread guards |
| OJS-PY-013 | Backend job ID vs local execution identity | UUID execution permits prevent duplicate IDs from overwriting active work |
| OJS-PY-014 | Unique policy model vs wire codec | `args_keys` and `meta_keys` round-trip symmetrically |
| OJS-PY-015 | Workflow builders vs enqueue options | Steps and callbacks derive from canonical `JobRequest` projection |
| OJS-PY-016 | Package facade vs metadata/export registry | Shared version source and deterministic lazy public export registry |
| OJS-PY-017 | Aggregate transport vs unsupported gRPC capabilities | Typed capability failures, pagination, workflow projection, and preserved SDK errors |
| OJS-PY-018 | AWS/Azure adapters vs shared invocation protocol | Shared parsing, registry, bridge, callbacks, and normalized error responses |
| OJS-PY-019 | Agent client vs core HTTP policy | Agent endpoints use the core request transport with quoted canonical paths |
| OJS-PY-020 | SSE connection ownership vs parser/error/reconnect policy | Injectable session actor, strict/raw malformed policy, typed errors, cancellation cleanup |
| OJS-PY-021 | Receipt signature vs claimed envelope | Versioned canonical attestation payload, freshness and full-claim verification |
| OJS-PY-022 | Production client vs process-global test state | Context-local fake transport; test assertions no longer own production routing |
| OJS-PY-023 | Local retry sleep vs visibility lease | Monotonic execution lease, heartbeat extension, expiry and cancellation handling |
| OJS-PY-024 | Source compatibility check vs shipped wheel | Removed unshipped duplicate and validate the built `ojs` package with Griffe |

### P2

| ID | actors in conflict / risk | outcome and evidence |
|---|---|---|
| OJS-PY-025 | Fat transport ABC vs narrow consumers | Public producer, worker, workflow, checkpoint, progress, and administration protocols |
| OJS-PY-026 | Module file vs package directory | Deleted shadowed `middleware.py`; import and wheel-content regressions added |
| OJS-PY-027 | Dynamic boundaries vs strict typing | Zero strict-mypy findings; only generated protobuf code has a narrow override |
| OJS-PY-028 | Test assertions vs production security lint | `S101` ignored only in tests; all other Ruff findings fixed |
| OJS-PY-029 | Functional edits vs deterministic style | Entire repository formatted; format check is clean |
| OJS-PY-030 | Wire payloads vs raw Python exceptions | Path-aware `WireDecoder` for Job, Workflow, Queue, QueueStats, and Event |
| OJS-PY-031 | Handler context vs worker internals | Clean public signature with deprecated runtime compatibility for legacy private keywords |
| OJS-PY-032 | Handler progress vs private transport access | `ctx.report_progress()` bound to an execution-scoped progress capability |
| OJS-PY-033 | Job outcome vs observability backend failures | Metrics fail open by default; explicit fail-closed mode and all-phase tests |
| OJS-PY-034 | Builtin `TimeoutError` vs SDK taxonomy | `JobExecutionTimeout` under `OJSTimeoutError`; legacy class remains catch-compatible |
| OJS-PY-035 | Retry policy vs RFC header forms | Numeric and HTTP-date `Retry-After` parsing with deterministic clock tests |
| OJS-PY-036 | Retry status vs operator logs | Structured `rate_limited` and `transient_server_error` reasons |
| OJS-PY-037 | Retry loop vs unreachable exhaustion branch | One reachable terminal mapping path; exact retry-count characterization |
| OJS-PY-038 | Timestamp normalization vs embedded `Z`/raw errors | Only terminal `Z` is rewritten; malformed values are path-aware SDK errors |
| OJS-PY-039 | Agent decorator claim vs actual durability | Clearly deprecated pass-through marker; real durability remains `DurableContext` |
| OJS-PY-040 | Documentation vs shipped APIs/gates | Correct middleware APIs, uv commands, honest type/coverage claims, example smoke tests |
| OJS-PY-041 | Build isolation vs reproducibility | Locked dependencies, pinned Hatchling/uv, two-build hash and member comparison |
| OJS-PY-042 | Optional features vs CI/publish confidence | Python/base/all-extras matrices, deterministic Bandit, audit and wheel import gates |
| OJS-PY-043 | Worker configuration vs delayed runtime failures | Eager positive/finite validation and normalized visibility timeout |

### Follow-up pass — protocol, concurrency, and taxonomy findings (OJS-PY-044 through OJS-PY-052)

A second, targeted review pass inspected serverless callback authentication,
Azure Service Bus/HTTP error classification, gRPC job/error projection
presence semantics, the batch enqueue middleware onion, SSE reconnection
state, and worker signal/heartbeat shutdown concurrency. All nine findings
below are implemented, tested, and merged into the actor ownership described
above; no new actor modules were required; each finding is a targeted
correctness fix within an existing actor's file.

| ID | actors in conflict / risk | outcome and evidence |
|---|---|---|
| OJS-PY-044 | Serverless completion callback auth vs OJS HTTP binding convention | `create_completion_transport` now derives `Authorization: Bearer <api_key>` instead of a bespoke `X-OJS-API-Key`-only header; an optional `headers` parameter on `LambdaHandler`/`AzureFunctionsHandler` is merged additively (an explicit caller-supplied `Authorization` header is never overridden by `api_key`). `tests/test_serverless.py` |
| OJS-PY-045 | Azure Service Bus/Storage Queue trigger redelivery vs OJS NACK outcome | `AzureFunctionsHandler.handle_queue_message` now re-raises (preserving the original exception as `__cause__`) only when the underlying failure is retryable — even after a successful NACK callback — so the Functions runtime abandons the message and it is redelivered; a non-retryable outcome (including a malformed body that never reaches a handler) completes the message instead of retrying a poison message forever. `InvocationOutcome` gained a `cause`/`retryable` accessor to carry this without changing the AWS/SQS `requires_redelivery` contract. `tests/test_serverless.py` |
| OJS-PY-046 | Azure HTTP push malformed JSON vs handler invocation boundary | `req.get_json()`'s raw `ValueError`/`json.JSONDecodeError` is now normalized into `ServerlessEventError` *before* the handler ever runs, classifying it as `invalid_request` (HTTP 400, non-retryable) the same way a malformed string/bytes body already was, instead of surfacing as an opaque retryable `handler_error` with a 200 status. `tests/test_serverless.py` |
| OJS-PY-047 | gRPC job projection vs protobuf zero-value presence | `project_job` now extracts protobuf messages with `always_print_fields_with_no_presence=True` and only substitutes a field in the projected dict when the source actually contains it, so an explicit `retry.max_attempts = 0`, `retry.backoff_coefficient = 0.0`, or job-level `max_attempts = 0` is preserved instead of being silently coerced to the hardcoded defaults `3`/`2.0`. Message-typed submessage presence (`retry_policy`, `unique_policy`) still governs whether a policy is projected at all, so a genuinely absent policy still defers to `RetryPolicy`/`Job`'s own SDK defaults. `JOB_STATE_UNSPECIFIED` and empty repeated `args_keys`/`meta_keys` are explicitly guarded so they keep resolving to their prior sentinel defaults rather than leaking a literal `"unspecified"` state or an incorrectly-restrictive empty list. `tests/test_transport_grpc.py::TestGrpcProjections` |
| OJS-PY-048 | `rpc_error_mapper` structured-detail decoding vs malformed trailers | `_structured_error` now catches `google.protobuf.message.DecodeError` (not a `ValueError` subclass) alongside `ValueError` when parsing a `grpc-status-details-bin` trailer, falling back to the ordinary gRPC status-code mapping instead of letting a raw protobuf decode error propagate out of `map_grpc_error` and mask the underlying gRPC status entirely. `tests/test_transport_grpc.py::TestErrorMapping` |
| OJS-PY-049 | Batch enqueue middleware onion vs one atomic transport call | `EnqueuePipeline.enqueue_batch` was rewritten around a barrier: every item's middleware chain runs concurrently up to its terminal `dispatch` call (validating and capturing the request), a single atomic `push_batch` is issued once every chain has reached its terminal (or the whole batch is aborted before any transport call if one is rejected/erred), and each terminal is then resolved with the *real* transport-returned `Job` — not a fabricated `__ojs_batch_pending_*` placeholder — so outer middleware's post-`next()` code observes genuine data and return-value transformations are honored. A pre-terminal `None` still aborts the whole batch (unchanged, existing semantics); a post-terminal `None` is a silent drop (the job was already durably created) rather than an error. Mirrors the JS SDK's `enqueueBatch` barrier. `tests/test_client.py::TestBatchMiddlewareBarrier` |
| OJS-PY-050 | SSE `id` field vs WHATWG "last event ID buffer" semantics | `SSEFrameParser` now tracks a sticky last-event-ID buffer (seeded per connection from the session's current value) that persists across dispatches instead of resetting per block: a block with no `id` field inherits the buffer: a block with an explicit-but-empty `id` (bare `id` or `id:`) resets it to the empty string, matching the WHATWG worked example distinguishing "absent" from "explicit empty". `SubscriptionSession.events()` now tracks `last_event_id` unconditionally from each event so a reconnect after an explicit reset correctly omits the `Last-Event-ID` header instead of resending a now-stale value. `tests/test_subscribe.py` |
| OJS-PY-051 | SSE HTTP 204 vs reconnect policy | A `204 No Content` response — the SSE spec's explicit "stop reconnecting" signal — now raises an internal terminal marker caught by `events()` to end the subscription unconditionally, regardless of the configured `reconnect`/`max_reconnects` policy; previously a 204 fell through as a clean, empty stream and reconnected like ordinary EOF. `tests/test_subscribe.py` |
| OJS-PY-052 | Worker signal/heartbeat concurrency vs public lifecycle state | Every shutdown trigger (OS signal, explicit `stop()`, and a server "terminate" heartbeat directive) now routes through a single synchronous `_request_termination` that publishes `WorkerState.TERMINATE` and requests the shutdown event with no `await` in between, so the two are atomic from the event loop's perspective. `_heartbeat_loop`'s "quiet"/"running" directive handling is now guarded behind `run_state.shutdown.is_set()`, so a heartbeat response already in flight when a signal arrives cannot overwrite `TERMINATE` with a stale directive after the fact. `tests/test_worker_lifecycle.py::TestSignalShutdownAtomicity` |

## Compatibility decisions

- Existing module, class, function, and method entry points are retained where
  possible. Former monoliths are package facades over actor modules.
- `JobContext` presents only handler state through `inspect.signature`, while
  legacy `_transport` and `_cancelled` keywords still work with a deprecation
  warning.
- `ojs.middleware.timeout.TimeoutError` remains a class and subclasses the new
  `JobExecutionTimeout`, so both old and new catch sites work.
- Unsupported gRPC operations fail with `OJSCapabilityError` instead of
  returning fabricated success.
- The historical `ojs.agent.durable` decorator remains exported but warns
  that it is pass-through; implementing false persistence semantics was
  rejected in favor of the real checkpoint/replay API.
- `create_completion_transport`/`LambdaHandler`/`AzureFunctionsHandler` no
  longer send `X-OJS-API-Key`; this is treated as an additive protocol
  correction (per the OJS HTTP binding's own `Authorization` convention)
  rather than a compatibility break, since no conformant OJS server
  authenticates against that bespoke header.
- The gRPC job projection's top-level `Job.max_attempts` field has no
  protobuf presence tracking of its own (only the `retry_policy` submessage
  does), so a bare, all-default protobuf `Job` message is wire-identical to
  one explicitly requesting zero attempts; the fix trusts the wire value
  verbatim in both cases rather than guessing the caller "must have meant"
  the SDK's default of 3. A plain `dict` source (not a protobuf message)
  that genuinely omits the key still defers to `Job`/`RetryPolicy`'s own
  defaults.
- A post-terminal `None` return from batch enqueue middleware (i.e., after
  the item's real transport push already atomically succeeded) is treated
  as a silent, no-error drop from the visible result list rather than
  raising, since the job was already durably created and cannot be
  "un-enqueued"; a pre-terminal `None` continues to abort the whole batch
  with an `OJSError`, unchanged from before.
- The SSE frame parser's sticky last-event-ID buffer is scoped per TCP
  connection (reseeded from the session's last known value on each
  reconnect), matching a fresh HTTP request/response cycle; it is not
  further updated by an `id` field seen only in a final, EOF-truncated
  frame that is discarded before its blank-line terminator, since exposing
  that edge case would require restructuring `_consume_once`'s generator
  boundary for a scenario the SSE spec's own worked examples do not cover.

## Verification evidence

Re-verified after the OJS-PY-044 through OJS-PY-052 follow-up pass (all
gates re-run from a clean environment against the current, still-unstaged
working tree):

| Gate | Outcome |
|---|---|
| `uv lock --check` | PASS |
| `uv run ruff check .` | PASS |
| `uv run ruff format --check .` | PASS, 140 files |
| `uv run mypy src` | PASS, 107 source files |
| `uv run griffe check -s src ojs --against HEAD` | PASS, no breaking changes |
| `uv run sphinx-build -W -b html docs docs/_build/html` | PASS |
| Python 3.11 full pytest + coverage | PASS, 678 passed / 25 skipped / 81.17% |
| Python 3.12 full pytest | PASS, 678 passed / 25 skipped |
| Python 3.13 full pytest | PASS, 678 passed / 25 skipped |
| Bandit (`bandit -r src/ojs -c pyproject.toml`) | PASS, zero findings |
| pip-audit | PASS, no known vulnerabilities |
| Reproducible wheel/sdist (`tools/check_reproducible_build.py`) | PASS, identical member content and SHA-256 across two clean builds |
| Base wheel install/import | PASS; `cryptography` remains unloaded |
| All-extras wheel install/import | PASS |
| All-extras sdist install/import | PASS |
| `git diff --check` | PASS |

Final wheel hash (from the reproducible two-build comparison above):

- Wheel: `sha256:8dae47a407bb126a0f58cae3660c1ab873efeb73d2061659012538b2adf8fc70`

The source-distribution hash is intentionally not embedded here:
`AUDIT.md` is itself included in the sdist, so recording the sdist's digest
inside this file would change the artifact and immediately make that digest
stale. The reproducibility gate compares both independently built sdist
archives byte-for-byte and prints their matching digest at execution time.

Python interpreter evidence: all three required versions (3.11.13, 3.12.13,
3.13.13) were available locally via `uv python list` and each was
`uv sync --locked --python <version> --all-extras --dev`'d and exercised
with the full test suite; no version was blocked or skipped.

## Assumptions

- A typed capability error is safer than silently dropping an option that the
  canonical gRPC service cannot represent.
- SSE reconnect remains opt-in so existing clean-EOF behavior is not changed
  accidentally.
- `grace_period=0` is a valid request for immediate worker shutdown, while
  polling, heartbeat, request, concurrency, and visibility values must be
  strictly positive.
- Generated protobuf files are vendored outputs; strict checking applies to
  handwritten integration code, with a narrowly scoped generated-module
  mypy override.
- Eliminating `X-OJS-API-Key` for the serverless completion callback is
  treated as a straightforward correction to match the OJS HTTP binding's
  own `Authorization` convention, not a supported alternate auth scheme
  worth preserving as a fallback.
- Azure Storage Queue and Service Bus queue triggers are treated
  identically by `handle_queue_message` (both use exception-based
  abandon/redeliver semantics in the Python Azure Functions worker), so one
  retryable-vs-non-retryable redelivery policy serves both trigger types
  without a separate entry point.
- A batch enqueue item that short-circuits *before* reaching its middleware
  terminal by returning a non-`None` value (a "replace" middleware that
  never calls `next()`) is honored as that fabricated result and is never
  sent to the transport, matching the existing single-item `enqueue()`
  "replace" semantics; only a pre-terminal `None` is treated as a rejection
  that aborts the whole batch.
- The worker's centralized `_request_termination` is the single place that
  publishes `WorkerState.TERMINATE`; an uncaught exception from the fetch or
  heartbeat loop (not a signal, `stop()`, or a server "terminate"
  directive) still requests shutdown via `ShutdownCoordinator`'s own
  `finally` block without first publishing `TERMINATE`, since that path is
  already collapsed into `IDLE` by `start()`'s own `finally` moments later
  and is a materially different, already-narrow race window than the one
  OJS-PY-052 targets.

## Deferred

No repository-local audit finding is deferred.

Live interoperability tests against every external OJS backend are not
possible in this repository-only pass; generated-protobuf round trips,
captured RPC requests, HTTP mocks, and transport parity fixtures provide the
local verification boundary.

The SSE frame parser's sticky last-event-ID buffer does not currently
propagate an `id` field seen only in a final, EOF-truncated frame (one
without its terminating blank line) into the next reconnect's
`Last-Event-ID` header, since that frame is discarded by `finish()` before
ever being dispatched as an event; see the corresponding compatibility
decision above. This is a narrow, spec-edge scenario (the WHATWG worked
examples do not cover a stream ending mid-frame with a still-meaningful
trailing `id`) and is called out here rather than silently left unhandled.

## Out of scope

- No sibling repository was edited.
- No remote service, release, or publish operation was performed.
- No files were staged or committed.
- External reusable organization workflows and backend implementations remain
  owned by their respective repositories.
