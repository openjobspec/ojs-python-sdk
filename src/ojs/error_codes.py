"""Standardized OJS error codes as defined in the OJS SDK Error Catalog.

See spec/ojs-error-catalog.md for the full specification. Each code maps
to a canonical wire-format string code from the OJS Error Specification.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ErrorCodeEntry:
    """A single entry in the OJS error catalog."""

    code: str
    """The OJS-XXXX numeric identifier (e.g., ``"OJS-1000"``)."""

    name: str
    """Human-readable error name (e.g., ``"InvalidPayload"``)."""

    canonical_code: str
    """SCREAMING_SNAKE_CASE wire-format code, or empty string for client-side errors."""

    http_status: int
    """Default HTTP status code, or 0 for client-side errors."""

    message: str
    """Default human-readable description."""

    retryable: bool
    """Default retryability."""


# ---------------------------------------------------------------------------
# OJS-1xxx: Client Errors
# ---------------------------------------------------------------------------

INVALID_PAYLOAD = ErrorCodeEntry("OJS-1000", "InvalidPayload", "INVALID_PAYLOAD", 400, "Job envelope fails structural validation", False)
INVALID_JOB_TYPE = ErrorCodeEntry("OJS-1001", "InvalidJobType", "INVALID_JOB_TYPE", 400, "Job type is not registered or does not match the allowlist", False)
INVALID_QUEUE = ErrorCodeEntry("OJS-1002", "InvalidQueue", "INVALID_QUEUE", 400, "Queue name is invalid or does not match naming rules", False)
INVALID_ARGS = ErrorCodeEntry("OJS-1003", "InvalidArgs", "INVALID_ARGS", 400, "Job args fail type checking or schema validation", False)
INVALID_METADATA = ErrorCodeEntry("OJS-1004", "InvalidMetadata", "INVALID_METADATA", 400, "Metadata field is malformed or exceeds the 64 KB size limit", False)
INVALID_STATE_TRANSITION = ErrorCodeEntry("OJS-1005", "InvalidStateTransition", "INVALID_STATE_TRANSITION", 409, "Attempted an invalid lifecycle state change", False)
INVALID_RETRY_POLICY = ErrorCodeEntry("OJS-1006", "InvalidRetryPolicy", "INVALID_RETRY_POLICY", 400, "Retry policy configuration is invalid", False)
INVALID_CRON_EXPRESSION = ErrorCodeEntry("OJS-1007", "InvalidCronExpression", "INVALID_CRON_EXPRESSION", 400, "Cron expression syntax cannot be parsed", False)
SCHEMA_VALIDATION_FAILED = ErrorCodeEntry("OJS-1008", "SchemaValidationFailed", "SCHEMA_VALIDATION_FAILED", 422, "Job args do not conform to the registered schema", False)
PAYLOAD_TOO_LARGE = ErrorCodeEntry("OJS-1009", "PayloadTooLarge", "PAYLOAD_TOO_LARGE", 413, "Job envelope exceeds the server's maximum payload size", False)
METADATA_TOO_LARGE = ErrorCodeEntry("OJS-1010", "MetadataTooLarge", "METADATA_TOO_LARGE", 413, "Metadata field exceeds the 64 KB limit", False)
CONNECTION_ERROR = ErrorCodeEntry("OJS-1011", "ConnectionError", "", 0, "Could not establish a connection to the OJS server", True)
REQUEST_TIMEOUT = ErrorCodeEntry("OJS-1012", "RequestTimeout", "", 0, "HTTP request to the OJS server timed out", True)
SERIALIZATION_ERROR = ErrorCodeEntry("OJS-1013", "SerializationError", "", 0, "Failed to serialize the request or deserialize the response", False)
QUEUE_NAME_TOO_LONG = ErrorCodeEntry("OJS-1014", "QueueNameTooLong", "QUEUE_NAME_TOO_LONG", 400, "Queue name exceeds the 255-byte maximum length", False)
JOB_TYPE_TOO_LONG = ErrorCodeEntry("OJS-1015", "JobTypeTooLong", "JOB_TYPE_TOO_LONG", 400, "Job type exceeds the 255-byte maximum length", False)
CHECKSUM_MISMATCH = ErrorCodeEntry("OJS-1016", "ChecksumMismatch", "CHECKSUM_MISMATCH", 400, "External payload reference checksum verification failed", False)
UNSUPPORTED_COMPRESSION = ErrorCodeEntry("OJS-1017", "UnsupportedCompression", "UNSUPPORTED_COMPRESSION", 400, "The specified compression codec is not supported", False)

# ---------------------------------------------------------------------------
# OJS-2xxx: Server Errors
# ---------------------------------------------------------------------------

BACKEND_ERROR = ErrorCodeEntry("OJS-2000", "BackendError", "BACKEND_ERROR", 500, "Internal backend storage or transport failure", True)
BACKEND_UNAVAILABLE = ErrorCodeEntry("OJS-2001", "BackendUnavailable", "BACKEND_UNAVAILABLE", 503, "Backend storage system is unreachable", True)
BACKEND_TIMEOUT = ErrorCodeEntry("OJS-2002", "BackendTimeout", "BACKEND_TIMEOUT", 504, "Backend operation timed out", True)
REPLICATION_LAG = ErrorCodeEntry("OJS-2003", "ReplicationLag", "REPLICATION_LAG", 500, "Operation failed due to replication consistency issue", True)
INTERNAL_SERVER_ERROR = ErrorCodeEntry("OJS-2004", "InternalServerError", "", 500, "Unclassified internal server error", True)

# ---------------------------------------------------------------------------
# OJS-3xxx: Job Lifecycle Errors
# ---------------------------------------------------------------------------

JOB_NOT_FOUND = ErrorCodeEntry("OJS-3000", "JobNotFound", "NOT_FOUND", 404, "The requested job, queue, or resource does not exist", False)
DUPLICATE_JOB = ErrorCodeEntry("OJS-3001", "DuplicateJob", "DUPLICATE_JOB", 409, "Unique job constraint was violated", False)
JOB_ALREADY_COMPLETED = ErrorCodeEntry("OJS-3002", "JobAlreadyCompleted", "JOB_ALREADY_COMPLETED", 409, "Operation attempted on a job that has already completed", False)
JOB_ALREADY_CANCELLED = ErrorCodeEntry("OJS-3003", "JobAlreadyCancelled", "JOB_ALREADY_CANCELLED", 409, "Operation attempted on a job that has already been cancelled", False)
QUEUE_PAUSED = ErrorCodeEntry("OJS-3004", "QueuePaused", "QUEUE_PAUSED", 422, "The target queue is paused and not accepting new jobs", True)
HANDLER_ERROR = ErrorCodeEntry("OJS-3005", "HandlerError", "HANDLER_ERROR", 0, "Job handler threw an exception during execution", True)
HANDLER_TIMEOUT = ErrorCodeEntry("OJS-3006", "HandlerTimeout", "HANDLER_TIMEOUT", 0, "Job handler exceeded the configured execution timeout", True)
HANDLER_PANIC = ErrorCodeEntry("OJS-3007", "HandlerPanic", "HANDLER_PANIC", 0, "Job handler caused an unrecoverable error", True)
NON_RETRYABLE_ERROR = ErrorCodeEntry("OJS-3008", "NonRetryableError", "NON_RETRYABLE_ERROR", 0, "Error type matched non_retryable_errors in the retry policy", False)
JOB_CANCELLED = ErrorCodeEntry("OJS-3009", "JobCancelled", "JOB_CANCELLED", 0, "Job was cancelled while it was executing", False)
NO_HANDLER_REGISTERED = ErrorCodeEntry("OJS-3010", "NoHandlerRegistered", "", 0, "No handler is registered for the received job type", False)

# ---------------------------------------------------------------------------
# OJS-4xxx: Workflow Errors
# ---------------------------------------------------------------------------

WORKFLOW_NOT_FOUND = ErrorCodeEntry("OJS-4000", "WorkflowNotFound", "", 404, "The specified workflow does not exist", False)
CHAIN_STEP_FAILED = ErrorCodeEntry("OJS-4001", "ChainStepFailed", "", 422, "A step in a chain workflow failed, halting subsequent steps", False)
GROUP_TIMEOUT = ErrorCodeEntry("OJS-4002", "GroupTimeout", "", 504, "A group workflow did not complete within the allowed timeout", True)
DEPENDENCY_FAILED = ErrorCodeEntry("OJS-4003", "DependencyFailed", "", 422, "A required dependency job failed, preventing execution", False)
CYCLIC_DEPENDENCY = ErrorCodeEntry("OJS-4004", "CyclicDependency", "", 400, "The workflow definition contains circular dependencies", False)
BATCH_CALLBACK_FAILED = ErrorCodeEntry("OJS-4005", "BatchCallbackFailed", "", 422, "The batch completion callback job failed", True)
WORKFLOW_CANCELLED = ErrorCodeEntry("OJS-4006", "WorkflowCancelled", "", 409, "The entire workflow was cancelled", False)

# ---------------------------------------------------------------------------
# OJS-5xxx: Authentication & Authorization Errors
# ---------------------------------------------------------------------------

UNAUTHENTICATED = ErrorCodeEntry("OJS-5000", "Unauthenticated", "UNAUTHENTICATED", 401, "No authentication credentials provided or credentials are invalid", False)
PERMISSION_DENIED = ErrorCodeEntry("OJS-5001", "PermissionDenied", "PERMISSION_DENIED", 403, "Authenticated but lacks the required permission", False)
TOKEN_EXPIRED = ErrorCodeEntry("OJS-5002", "TokenExpired", "TOKEN_EXPIRED", 401, "The authentication token has expired", False)
TENANT_ACCESS_DENIED = ErrorCodeEntry("OJS-5003", "TenantAccessDenied", "TENANT_ACCESS_DENIED", 403, "Operation on a tenant the caller does not have access to", False)

# ---------------------------------------------------------------------------
# OJS-6xxx: Rate Limiting & Backpressure Errors
# ---------------------------------------------------------------------------

RATE_LIMITED = ErrorCodeEntry("OJS-6000", "RateLimited", "RATE_LIMITED", 429, "Rate limit exceeded", True)
QUEUE_FULL = ErrorCodeEntry("OJS-6001", "QueueFull", "QUEUE_FULL", 429, "The queue has reached its configured maximum depth", True)
CONCURRENCY_LIMITED = ErrorCodeEntry("OJS-6002", "ConcurrencyLimited", "", 429, "The concurrency limit has been reached", True)
BACKPRESSURE_APPLIED = ErrorCodeEntry("OJS-6003", "BackpressureApplied", "", 429, "The server is applying backpressure", True)

# ---------------------------------------------------------------------------
# OJS-7xxx: Extension Errors
# ---------------------------------------------------------------------------

UNSUPPORTED_FEATURE = ErrorCodeEntry("OJS-7000", "UnsupportedFeature", "UNSUPPORTED_FEATURE", 422, "Feature requires a conformance level the backend does not support", False)
CRON_SCHEDULE_CONFLICT = ErrorCodeEntry("OJS-7001", "CronScheduleConflict", "", 409, "The cron schedule conflicts with an existing schedule", False)
UNIQUE_KEY_INVALID = ErrorCodeEntry("OJS-7002", "UniqueKeyInvalid", "", 400, "The unique key specification is invalid or malformed", False)
MIDDLEWARE_ERROR = ErrorCodeEntry("OJS-7003", "MiddlewareError", "", 500, "An error occurred in the middleware chain", True)
MIDDLEWARE_TIMEOUT = ErrorCodeEntry("OJS-7004", "MiddlewareTimeout", "", 504, "A middleware handler exceeded its allowed execution time", True)

# ---------------------------------------------------------------------------
# Catalog utilities
# ---------------------------------------------------------------------------

ALL_ERROR_CODES: tuple[ErrorCodeEntry, ...] = (
    # OJS-1xxx
    INVALID_PAYLOAD, INVALID_JOB_TYPE, INVALID_QUEUE, INVALID_ARGS,
    INVALID_METADATA, INVALID_STATE_TRANSITION, INVALID_RETRY_POLICY,
    INVALID_CRON_EXPRESSION, SCHEMA_VALIDATION_FAILED, PAYLOAD_TOO_LARGE,
    METADATA_TOO_LARGE, CONNECTION_ERROR, REQUEST_TIMEOUT, SERIALIZATION_ERROR,
    QUEUE_NAME_TOO_LONG, JOB_TYPE_TOO_LONG, CHECKSUM_MISMATCH, UNSUPPORTED_COMPRESSION,
    # OJS-2xxx
    BACKEND_ERROR, BACKEND_UNAVAILABLE, BACKEND_TIMEOUT, REPLICATION_LAG,
    INTERNAL_SERVER_ERROR,
    # OJS-3xxx
    JOB_NOT_FOUND, DUPLICATE_JOB, JOB_ALREADY_COMPLETED, JOB_ALREADY_CANCELLED,
    QUEUE_PAUSED, HANDLER_ERROR, HANDLER_TIMEOUT, HANDLER_PANIC,
    NON_RETRYABLE_ERROR, JOB_CANCELLED, NO_HANDLER_REGISTERED,
    # OJS-4xxx
    WORKFLOW_NOT_FOUND, CHAIN_STEP_FAILED, GROUP_TIMEOUT, DEPENDENCY_FAILED,
    CYCLIC_DEPENDENCY, BATCH_CALLBACK_FAILED, WORKFLOW_CANCELLED,
    # OJS-5xxx
    UNAUTHENTICATED, PERMISSION_DENIED, TOKEN_EXPIRED, TENANT_ACCESS_DENIED,
    # OJS-6xxx
    RATE_LIMITED, QUEUE_FULL, CONCURRENCY_LIMITED, BACKPRESSURE_APPLIED,
    # OJS-7xxx
    UNSUPPORTED_FEATURE, CRON_SCHEDULE_CONFLICT, UNIQUE_KEY_INVALID,
    MIDDLEWARE_ERROR, MIDDLEWARE_TIMEOUT,
)

_CANONICAL_INDEX: dict[str, ErrorCodeEntry] = {
    e.canonical_code: e for e in ALL_ERROR_CODES if e.canonical_code
}

_CODE_INDEX: dict[str, ErrorCodeEntry] = {e.code: e for e in ALL_ERROR_CODES}


def lookup_by_canonical_code(canonical_code: str) -> Optional[ErrorCodeEntry]:
    """Look up an entry by its canonical wire-format code (e.g., ``"INVALID_PAYLOAD"``)."""
    return _CANONICAL_INDEX.get(canonical_code)


def lookup_by_code(code: str) -> Optional[ErrorCodeEntry]:
    """Look up an entry by its OJS-XXXX numeric code (e.g., ``"OJS-1000"``)."""
    return _CODE_INDEX.get(code)
