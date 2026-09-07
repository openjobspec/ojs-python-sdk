import datetime

from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class JobState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    JOB_STATE_UNSPECIFIED: _ClassVar[JobState]
    JOB_STATE_SCHEDULED: _ClassVar[JobState]
    JOB_STATE_AVAILABLE: _ClassVar[JobState]
    JOB_STATE_PENDING: _ClassVar[JobState]
    JOB_STATE_ACTIVE: _ClassVar[JobState]
    JOB_STATE_COMPLETED: _ClassVar[JobState]
    JOB_STATE_RETRYABLE: _ClassVar[JobState]
    JOB_STATE_CANCELLED: _ClassVar[JobState]
    JOB_STATE_DISCARDED: _ClassVar[JobState]

class UniqueConflictAction(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    UNIQUE_CONFLICT_ACTION_UNSPECIFIED: _ClassVar[UniqueConflictAction]
    UNIQUE_CONFLICT_ACTION_REJECT: _ClassVar[UniqueConflictAction]
    UNIQUE_CONFLICT_ACTION_REPLACE: _ClassVar[UniqueConflictAction]
    UNIQUE_CONFLICT_ACTION_IGNORE: _ClassVar[UniqueConflictAction]
    UNIQUE_CONFLICT_ACTION_REPLACE_EXCEPT_SCHEDULE: _ClassVar[UniqueConflictAction]
JOB_STATE_UNSPECIFIED: JobState
JOB_STATE_SCHEDULED: JobState
JOB_STATE_AVAILABLE: JobState
JOB_STATE_PENDING: JobState
JOB_STATE_ACTIVE: JobState
JOB_STATE_COMPLETED: JobState
JOB_STATE_RETRYABLE: JobState
JOB_STATE_CANCELLED: JobState
JOB_STATE_DISCARDED: JobState
UNIQUE_CONFLICT_ACTION_UNSPECIFIED: UniqueConflictAction
UNIQUE_CONFLICT_ACTION_REJECT: UniqueConflictAction
UNIQUE_CONFLICT_ACTION_REPLACE: UniqueConflictAction
UNIQUE_CONFLICT_ACTION_IGNORE: UniqueConflictAction
UNIQUE_CONFLICT_ACTION_REPLACE_EXCEPT_SCHEDULE: UniqueConflictAction

class Job(_message.Message):
    __slots__ = ("id", "type", "queue", "args", "meta", "state", "priority", "attempt", "max_attempts", "retry_policy", "unique_policy", "result", "errors", "created_at", "enqueued_at", "scheduled_at", "started_at", "completed_at", "expires_at", "timeout", "visibility_timeout", "tags", "trace_id", "workflow_id", "specversion")
    ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    QUEUE_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    META_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    ATTEMPT_FIELD_NUMBER: _ClassVar[int]
    MAX_ATTEMPTS_FIELD_NUMBER: _ClassVar[int]
    RETRY_POLICY_FIELD_NUMBER: _ClassVar[int]
    UNIQUE_POLICY_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    ENQUEUED_AT_FIELD_NUMBER: _ClassVar[int]
    SCHEDULED_AT_FIELD_NUMBER: _ClassVar[int]
    STARTED_AT_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_AT_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    VISIBILITY_TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    SPECVERSION_FIELD_NUMBER: _ClassVar[int]
    id: str
    type: str
    queue: str
    args: _containers.RepeatedCompositeFieldContainer[_struct_pb2.Value]
    meta: _struct_pb2.Struct
    state: JobState
    priority: int
    attempt: int
    max_attempts: int
    retry_policy: RetryPolicy
    unique_policy: UniquePolicy
    result: _struct_pb2.Struct
    errors: _containers.RepeatedCompositeFieldContainer[JobError]
    created_at: _timestamp_pb2.Timestamp
    enqueued_at: _timestamp_pb2.Timestamp
    scheduled_at: _timestamp_pb2.Timestamp
    started_at: _timestamp_pb2.Timestamp
    completed_at: _timestamp_pb2.Timestamp
    expires_at: _timestamp_pb2.Timestamp
    timeout: _duration_pb2.Duration
    visibility_timeout: _duration_pb2.Duration
    tags: _containers.RepeatedScalarFieldContainer[str]
    trace_id: str
    workflow_id: str
    specversion: str
    def __init__(self, id: _Optional[str] = ..., type: _Optional[str] = ..., queue: _Optional[str] = ..., args: _Optional[_Iterable[_Union[_struct_pb2.Value, _Mapping]]] = ..., meta: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., state: _Optional[_Union[JobState, str]] = ..., priority: _Optional[int] = ..., attempt: _Optional[int] = ..., max_attempts: _Optional[int] = ..., retry_policy: _Optional[_Union[RetryPolicy, _Mapping]] = ..., unique_policy: _Optional[_Union[UniquePolicy, _Mapping]] = ..., result: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., errors: _Optional[_Iterable[_Union[JobError, _Mapping]]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., enqueued_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., scheduled_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., started_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., completed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., expires_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., timeout: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., visibility_timeout: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., tags: _Optional[_Iterable[str]] = ..., trace_id: _Optional[str] = ..., workflow_id: _Optional[str] = ..., specversion: _Optional[str] = ...) -> None: ...

class RetryPolicy(_message.Message):
    __slots__ = ("max_attempts", "initial_interval", "backoff_coefficient", "max_interval", "jitter", "non_retryable_errors", "on_exhaustion")
    MAX_ATTEMPTS_FIELD_NUMBER: _ClassVar[int]
    INITIAL_INTERVAL_FIELD_NUMBER: _ClassVar[int]
    BACKOFF_COEFFICIENT_FIELD_NUMBER: _ClassVar[int]
    MAX_INTERVAL_FIELD_NUMBER: _ClassVar[int]
    JITTER_FIELD_NUMBER: _ClassVar[int]
    NON_RETRYABLE_ERRORS_FIELD_NUMBER: _ClassVar[int]
    ON_EXHAUSTION_FIELD_NUMBER: _ClassVar[int]
    max_attempts: int
    initial_interval: _duration_pb2.Duration
    backoff_coefficient: float
    max_interval: _duration_pb2.Duration
    jitter: bool
    non_retryable_errors: _containers.RepeatedScalarFieldContainer[str]
    on_exhaustion: str
    def __init__(self, max_attempts: _Optional[int] = ..., initial_interval: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., backoff_coefficient: _Optional[float] = ..., max_interval: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., jitter: _Optional[bool] = ..., non_retryable_errors: _Optional[_Iterable[str]] = ..., on_exhaustion: _Optional[str] = ...) -> None: ...

class UniquePolicy(_message.Message):
    __slots__ = ("key", "period", "on_conflict", "states", "args_keys", "meta_keys")
    KEY_FIELD_NUMBER: _ClassVar[int]
    PERIOD_FIELD_NUMBER: _ClassVar[int]
    ON_CONFLICT_FIELD_NUMBER: _ClassVar[int]
    STATES_FIELD_NUMBER: _ClassVar[int]
    ARGS_KEYS_FIELD_NUMBER: _ClassVar[int]
    META_KEYS_FIELD_NUMBER: _ClassVar[int]
    key: _containers.RepeatedScalarFieldContainer[str]
    period: _duration_pb2.Duration
    on_conflict: UniqueConflictAction
    states: _containers.RepeatedScalarFieldContainer[JobState]
    args_keys: _containers.RepeatedScalarFieldContainer[str]
    meta_keys: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, key: _Optional[_Iterable[str]] = ..., period: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., on_conflict: _Optional[_Union[UniqueConflictAction, str]] = ..., states: _Optional[_Iterable[_Union[JobState, str]]] = ..., args_keys: _Optional[_Iterable[str]] = ..., meta_keys: _Optional[_Iterable[str]] = ...) -> None: ...

class JobError(_message.Message):
    __slots__ = ("code", "message", "retryable", "attempt", "occurred_at", "backtrace", "details")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    RETRYABLE_FIELD_NUMBER: _ClassVar[int]
    ATTEMPT_FIELD_NUMBER: _ClassVar[int]
    OCCURRED_AT_FIELD_NUMBER: _ClassVar[int]
    BACKTRACE_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    code: str
    message: str
    retryable: bool
    attempt: int
    occurred_at: _timestamp_pb2.Timestamp
    backtrace: str
    details: _struct_pb2.Struct
    def __init__(self, code: _Optional[str] = ..., message: _Optional[str] = ..., retryable: _Optional[bool] = ..., attempt: _Optional[int] = ..., occurred_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., backtrace: _Optional[str] = ..., details: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class EnqueueOptions(_message.Message):
    __slots__ = ("queue", "priority", "delay_until", "timeout", "retry", "unique", "ttl", "tags", "trace_id", "meta", "max_attempts", "visibility_timeout")
    QUEUE_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_FIELD_NUMBER: _ClassVar[int]
    DELAY_UNTIL_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    RETRY_FIELD_NUMBER: _ClassVar[int]
    UNIQUE_FIELD_NUMBER: _ClassVar[int]
    TTL_FIELD_NUMBER: _ClassVar[int]
    TAGS_FIELD_NUMBER: _ClassVar[int]
    TRACE_ID_FIELD_NUMBER: _ClassVar[int]
    META_FIELD_NUMBER: _ClassVar[int]
    MAX_ATTEMPTS_FIELD_NUMBER: _ClassVar[int]
    VISIBILITY_TIMEOUT_FIELD_NUMBER: _ClassVar[int]
    queue: str
    priority: int
    delay_until: _timestamp_pb2.Timestamp
    timeout: _duration_pb2.Duration
    retry: RetryPolicy
    unique: UniquePolicy
    ttl: _duration_pb2.Duration
    tags: _containers.RepeatedScalarFieldContainer[str]
    trace_id: str
    meta: _struct_pb2.Struct
    max_attempts: int
    visibility_timeout: _duration_pb2.Duration
    def __init__(self, queue: _Optional[str] = ..., priority: _Optional[int] = ..., delay_until: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., timeout: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., retry: _Optional[_Union[RetryPolicy, _Mapping]] = ..., unique: _Optional[_Union[UniquePolicy, _Mapping]] = ..., ttl: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., tags: _Optional[_Iterable[str]] = ..., trace_id: _Optional[str] = ..., meta: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., max_attempts: _Optional[int] = ..., visibility_timeout: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ...) -> None: ...

class EnqueueRequest(_message.Message):
    __slots__ = ("type", "args", "options")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    type: str
    args: _containers.RepeatedCompositeFieldContainer[_struct_pb2.Value]
    options: EnqueueOptions
    def __init__(self, type: _Optional[str] = ..., args: _Optional[_Iterable[_Union[_struct_pb2.Value, _Mapping]]] = ..., options: _Optional[_Union[EnqueueOptions, _Mapping]] = ...) -> None: ...

class EnqueueResponse(_message.Message):
    __slots__ = ("job",)
    JOB_FIELD_NUMBER: _ClassVar[int]
    job: Job
    def __init__(self, job: _Optional[_Union[Job, _Mapping]] = ...) -> None: ...

class EnqueueBatchRequest(_message.Message):
    __slots__ = ("jobs", "default_options")
    JOBS_FIELD_NUMBER: _ClassVar[int]
    DEFAULT_OPTIONS_FIELD_NUMBER: _ClassVar[int]
    jobs: _containers.RepeatedCompositeFieldContainer[BatchJobEntry]
    default_options: EnqueueOptions
    def __init__(self, jobs: _Optional[_Iterable[_Union[BatchJobEntry, _Mapping]]] = ..., default_options: _Optional[_Union[EnqueueOptions, _Mapping]] = ...) -> None: ...

class BatchJobEntry(_message.Message):
    __slots__ = ("type", "args", "options")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    type: str
    args: _containers.RepeatedCompositeFieldContainer[_struct_pb2.Value]
    options: EnqueueOptions
    def __init__(self, type: _Optional[str] = ..., args: _Optional[_Iterable[_Union[_struct_pb2.Value, _Mapping]]] = ..., options: _Optional[_Union[EnqueueOptions, _Mapping]] = ...) -> None: ...

class EnqueueBatchResponse(_message.Message):
    __slots__ = ("jobs", "count", "errors")
    class ErrorsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: int
        value: BatchJobError
        def __init__(self, key: _Optional[int] = ..., value: _Optional[_Union[BatchJobError, _Mapping]] = ...) -> None: ...
    JOBS_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    ERRORS_FIELD_NUMBER: _ClassVar[int]
    jobs: _containers.RepeatedCompositeFieldContainer[Job]
    count: int
    errors: _containers.MessageMap[int, BatchJobError]
    def __init__(self, jobs: _Optional[_Iterable[_Union[Job, _Mapping]]] = ..., count: _Optional[int] = ..., errors: _Optional[_Mapping[int, BatchJobError]] = ...) -> None: ...

class BatchJobError(_message.Message):
    __slots__ = ("code", "message")
    CODE_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    code: str
    message: str
    def __init__(self, code: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...

class GetJobRequest(_message.Message):
    __slots__ = ("job_id",)
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    def __init__(self, job_id: _Optional[str] = ...) -> None: ...

class GetJobResponse(_message.Message):
    __slots__ = ("job",)
    JOB_FIELD_NUMBER: _ClassVar[int]
    job: Job
    def __init__(self, job: _Optional[_Union[Job, _Mapping]] = ...) -> None: ...

class CancelJobRequest(_message.Message):
    __slots__ = ("job_id", "reason")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    reason: str
    def __init__(self, job_id: _Optional[str] = ..., reason: _Optional[str] = ...) -> None: ...

class CancelJobResponse(_message.Message):
    __slots__ = ("job",)
    JOB_FIELD_NUMBER: _ClassVar[int]
    job: Job
    def __init__(self, job: _Optional[_Union[Job, _Mapping]] = ...) -> None: ...
