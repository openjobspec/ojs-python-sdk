import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from ojs._generated.ojs.v1 import job_pb2 as _job_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ListQueuesRequest(_message.Message):
    __slots__ = ("limit", "cursor")
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    CURSOR_FIELD_NUMBER: _ClassVar[int]
    limit: int
    cursor: str
    def __init__(self, limit: _Optional[int] = ..., cursor: _Optional[str] = ...) -> None: ...

class ListQueuesResponse(_message.Message):
    __slots__ = ("queues", "next_cursor")
    QUEUES_FIELD_NUMBER: _ClassVar[int]
    NEXT_CURSOR_FIELD_NUMBER: _ClassVar[int]
    queues: _containers.RepeatedCompositeFieldContainer[QueueInfo]
    next_cursor: str
    def __init__(self, queues: _Optional[_Iterable[_Union[QueueInfo, _Mapping]]] = ..., next_cursor: _Optional[str] = ...) -> None: ...

class QueueInfo(_message.Message):
    __slots__ = ("name", "paused", "available_count", "created_at")
    NAME_FIELD_NUMBER: _ClassVar[int]
    PAUSED_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_COUNT_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    name: str
    paused: bool
    available_count: int
    created_at: _timestamp_pb2.Timestamp
    def __init__(self, name: _Optional[str] = ..., paused: _Optional[bool] = ..., available_count: _Optional[int] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class QueueStatsRequest(_message.Message):
    __slots__ = ("queue",)
    QUEUE_FIELD_NUMBER: _ClassVar[int]
    queue: str
    def __init__(self, queue: _Optional[str] = ...) -> None: ...

class QueueStatsResponse(_message.Message):
    __slots__ = ("queue", "stats")
    QUEUE_FIELD_NUMBER: _ClassVar[int]
    STATS_FIELD_NUMBER: _ClassVar[int]
    queue: str
    stats: QueueStatistics
    def __init__(self, queue: _Optional[str] = ..., stats: _Optional[_Union[QueueStatistics, _Mapping]] = ...) -> None: ...

class QueueStatistics(_message.Message):
    __slots__ = ("available", "active", "scheduled", "retryable", "dead", "completed_last_hour", "failed_last_hour", "avg_duration_ms", "avg_wait_ms", "throughput_per_second", "paused")
    AVAILABLE_FIELD_NUMBER: _ClassVar[int]
    ACTIVE_FIELD_NUMBER: _ClassVar[int]
    SCHEDULED_FIELD_NUMBER: _ClassVar[int]
    RETRYABLE_FIELD_NUMBER: _ClassVar[int]
    DEAD_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_LAST_HOUR_FIELD_NUMBER: _ClassVar[int]
    FAILED_LAST_HOUR_FIELD_NUMBER: _ClassVar[int]
    AVG_DURATION_MS_FIELD_NUMBER: _ClassVar[int]
    AVG_WAIT_MS_FIELD_NUMBER: _ClassVar[int]
    THROUGHPUT_PER_SECOND_FIELD_NUMBER: _ClassVar[int]
    PAUSED_FIELD_NUMBER: _ClassVar[int]
    available: int
    active: int
    scheduled: int
    retryable: int
    dead: int
    completed_last_hour: int
    failed_last_hour: int
    avg_duration_ms: float
    avg_wait_ms: float
    throughput_per_second: float
    paused: bool
    def __init__(self, available: _Optional[int] = ..., active: _Optional[int] = ..., scheduled: _Optional[int] = ..., retryable: _Optional[int] = ..., dead: _Optional[int] = ..., completed_last_hour: _Optional[int] = ..., failed_last_hour: _Optional[int] = ..., avg_duration_ms: _Optional[float] = ..., avg_wait_ms: _Optional[float] = ..., throughput_per_second: _Optional[float] = ..., paused: _Optional[bool] = ...) -> None: ...

class PauseQueueRequest(_message.Message):
    __slots__ = ("queue",)
    QUEUE_FIELD_NUMBER: _ClassVar[int]
    queue: str
    def __init__(self, queue: _Optional[str] = ...) -> None: ...

class PauseQueueResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ResumeQueueRequest(_message.Message):
    __slots__ = ("queue",)
    QUEUE_FIELD_NUMBER: _ClassVar[int]
    queue: str
    def __init__(self, queue: _Optional[str] = ...) -> None: ...

class ResumeQueueResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListDeadLetterRequest(_message.Message):
    __slots__ = ("queue", "limit", "cursor")
    QUEUE_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    CURSOR_FIELD_NUMBER: _ClassVar[int]
    queue: str
    limit: int
    cursor: str
    def __init__(self, queue: _Optional[str] = ..., limit: _Optional[int] = ..., cursor: _Optional[str] = ...) -> None: ...

class ListDeadLetterResponse(_message.Message):
    __slots__ = ("jobs", "total_count", "next_cursor")
    JOBS_FIELD_NUMBER: _ClassVar[int]
    TOTAL_COUNT_FIELD_NUMBER: _ClassVar[int]
    NEXT_CURSOR_FIELD_NUMBER: _ClassVar[int]
    jobs: _containers.RepeatedCompositeFieldContainer[_job_pb2.Job]
    total_count: int
    next_cursor: str
    def __init__(self, jobs: _Optional[_Iterable[_Union[_job_pb2.Job, _Mapping]]] = ..., total_count: _Optional[int] = ..., next_cursor: _Optional[str] = ...) -> None: ...

class RetryDeadLetterRequest(_message.Message):
    __slots__ = ("job_id",)
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    def __init__(self, job_id: _Optional[str] = ...) -> None: ...

class RetryDeadLetterResponse(_message.Message):
    __slots__ = ("job",)
    JOB_FIELD_NUMBER: _ClassVar[int]
    job: _job_pb2.Job
    def __init__(self, job: _Optional[_Union[_job_pb2.Job, _Mapping]] = ...) -> None: ...

class DeleteDeadLetterRequest(_message.Message):
    __slots__ = ("job_id",)
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    def __init__(self, job_id: _Optional[str] = ...) -> None: ...

class DeleteDeadLetterResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
