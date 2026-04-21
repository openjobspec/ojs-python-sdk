import datetime

from google.protobuf import duration_pb2 as _duration_pb2
from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from ojs._generated.ojs.v1 import job_pb2 as _job_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class WorkerState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WORKER_STATE_UNSPECIFIED: _ClassVar[WorkerState]
    WORKER_STATE_RUNNING: _ClassVar[WorkerState]
    WORKER_STATE_QUIET: _ClassVar[WorkerState]
    WORKER_STATE_TERMINATE: _ClassVar[WorkerState]
WORKER_STATE_UNSPECIFIED: WorkerState
WORKER_STATE_RUNNING: WorkerState
WORKER_STATE_QUIET: WorkerState
WORKER_STATE_TERMINATE: WorkerState

class FetchRequest(_message.Message):
    __slots__ = ("queues", "count", "worker_id")
    QUEUES_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    WORKER_ID_FIELD_NUMBER: _ClassVar[int]
    queues: _containers.RepeatedScalarFieldContainer[str]
    count: int
    worker_id: str
    def __init__(self, queues: _Optional[_Iterable[str]] = ..., count: _Optional[int] = ..., worker_id: _Optional[str] = ...) -> None: ...

class FetchResponse(_message.Message):
    __slots__ = ("jobs",)
    JOBS_FIELD_NUMBER: _ClassVar[int]
    jobs: _containers.RepeatedCompositeFieldContainer[_job_pb2.Job]
    def __init__(self, jobs: _Optional[_Iterable[_Union[_job_pb2.Job, _Mapping]]] = ...) -> None: ...

class AckRequest(_message.Message):
    __slots__ = ("job_id", "result")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    RESULT_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    result: _struct_pb2.Struct
    def __init__(self, job_id: _Optional[str] = ..., result: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class AckResponse(_message.Message):
    __slots__ = ("acknowledged",)
    ACKNOWLEDGED_FIELD_NUMBER: _ClassVar[int]
    acknowledged: bool
    def __init__(self, acknowledged: _Optional[bool] = ...) -> None: ...

class NackRequest(_message.Message):
    __slots__ = ("job_id", "error")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    error: _job_pb2.JobError
    def __init__(self, job_id: _Optional[str] = ..., error: _Optional[_Union[_job_pb2.JobError, _Mapping]] = ...) -> None: ...

class NackResponse(_message.Message):
    __slots__ = ("state", "next_attempt_at")
    STATE_FIELD_NUMBER: _ClassVar[int]
    NEXT_ATTEMPT_AT_FIELD_NUMBER: _ClassVar[int]
    state: _job_pb2.JobState
    next_attempt_at: _timestamp_pb2.Timestamp
    def __init__(self, state: _Optional[_Union[_job_pb2.JobState, str]] = ..., next_attempt_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class HeartbeatRequest(_message.Message):
    __slots__ = ("id", "worker_id", "extend_by", "current_state")
    ID_FIELD_NUMBER: _ClassVar[int]
    WORKER_ID_FIELD_NUMBER: _ClassVar[int]
    EXTEND_BY_FIELD_NUMBER: _ClassVar[int]
    CURRENT_STATE_FIELD_NUMBER: _ClassVar[int]
    id: str
    worker_id: str
    extend_by: _duration_pb2.Duration
    current_state: WorkerState
    def __init__(self, id: _Optional[str] = ..., worker_id: _Optional[str] = ..., extend_by: _Optional[_Union[datetime.timedelta, _duration_pb2.Duration, _Mapping]] = ..., current_state: _Optional[_Union[WorkerState, str]] = ...) -> None: ...

class HeartbeatResponse(_message.Message):
    __slots__ = ("directed_state", "new_deadline")
    DIRECTED_STATE_FIELD_NUMBER: _ClassVar[int]
    NEW_DEADLINE_FIELD_NUMBER: _ClassVar[int]
    directed_state: WorkerState
    new_deadline: _timestamp_pb2.Timestamp
    def __init__(self, directed_state: _Optional[_Union[WorkerState, str]] = ..., new_deadline: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class StreamJobsRequest(_message.Message):
    __slots__ = ("queues", "worker_id", "max_concurrent")
    QUEUES_FIELD_NUMBER: _ClassVar[int]
    WORKER_ID_FIELD_NUMBER: _ClassVar[int]
    MAX_CONCURRENT_FIELD_NUMBER: _ClassVar[int]
    queues: _containers.RepeatedScalarFieldContainer[str]
    worker_id: str
    max_concurrent: int
    def __init__(self, queues: _Optional[_Iterable[str]] = ..., worker_id: _Optional[str] = ..., max_concurrent: _Optional[int] = ...) -> None: ...
