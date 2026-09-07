import datetime

from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from ojs._generated.ojs.v1 import events_pb2 as _events_pb2
from ojs._generated.ojs.v1 import job_pb2 as _job_pb2
from ojs._generated.ojs.v1 import queue_pb2 as _queue_pb2
from ojs._generated.ojs.v1 import worker_pb2 as _worker_pb2
from ojs._generated.ojs.v1 import workflow_pb2 as _workflow_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class HealthStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    HEALTH_STATUS_UNSPECIFIED: _ClassVar[HealthStatus]
    HEALTH_STATUS_OK: _ClassVar[HealthStatus]
    HEALTH_STATUS_DEGRADED: _ClassVar[HealthStatus]
    HEALTH_STATUS_UNHEALTHY: _ClassVar[HealthStatus]
HEALTH_STATUS_UNSPECIFIED: HealthStatus
HEALTH_STATUS_OK: HealthStatus
HEALTH_STATUS_DEGRADED: HealthStatus
HEALTH_STATUS_UNHEALTHY: HealthStatus

class ManifestRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ManifestResponse(_message.Message):
    __slots__ = ("ojs_version", "implementation", "conformance_level", "protocols", "backend", "extensions", "schema_validation")
    OJS_VERSION_FIELD_NUMBER: _ClassVar[int]
    IMPLEMENTATION_FIELD_NUMBER: _ClassVar[int]
    CONFORMANCE_LEVEL_FIELD_NUMBER: _ClassVar[int]
    PROTOCOLS_FIELD_NUMBER: _ClassVar[int]
    BACKEND_FIELD_NUMBER: _ClassVar[int]
    EXTENSIONS_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_VALIDATION_FIELD_NUMBER: _ClassVar[int]
    ojs_version: str
    implementation: Implementation
    conformance_level: int
    protocols: _containers.RepeatedScalarFieldContainer[str]
    backend: str
    extensions: _containers.RepeatedScalarFieldContainer[str]
    schema_validation: bool
    def __init__(self, ojs_version: _Optional[str] = ..., implementation: _Optional[_Union[Implementation, _Mapping]] = ..., conformance_level: _Optional[int] = ..., protocols: _Optional[_Iterable[str]] = ..., backend: _Optional[str] = ..., extensions: _Optional[_Iterable[str]] = ..., schema_validation: _Optional[bool] = ...) -> None: ...

class Implementation(_message.Message):
    __slots__ = ("name", "version", "language")
    NAME_FIELD_NUMBER: _ClassVar[int]
    VERSION_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    name: str
    version: str
    language: str
    def __init__(self, name: _Optional[str] = ..., version: _Optional[str] = ..., language: _Optional[str] = ...) -> None: ...

class HealthRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class HealthResponse(_message.Message):
    __slots__ = ("status", "timestamp", "details")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    status: HealthStatus
    timestamp: _timestamp_pb2.Timestamp
    details: _struct_pb2.Struct
    def __init__(self, status: _Optional[_Union[HealthStatus, str]] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., details: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class RegisterCronRequest(_message.Message):
    __slots__ = ("name", "cron", "timezone", "type", "args", "options")
    NAME_FIELD_NUMBER: _ClassVar[int]
    CRON_FIELD_NUMBER: _ClassVar[int]
    TIMEZONE_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    name: str
    cron: str
    timezone: str
    type: str
    args: _containers.RepeatedCompositeFieldContainer[_struct_pb2.Value]
    options: _job_pb2.EnqueueOptions
    def __init__(self, name: _Optional[str] = ..., cron: _Optional[str] = ..., timezone: _Optional[str] = ..., type: _Optional[str] = ..., args: _Optional[_Iterable[_Union[_struct_pb2.Value, _Mapping]]] = ..., options: _Optional[_Union[_job_pb2.EnqueueOptions, _Mapping]] = ...) -> None: ...

class RegisterCronResponse(_message.Message):
    __slots__ = ("name", "next_run_at")
    NAME_FIELD_NUMBER: _ClassVar[int]
    NEXT_RUN_AT_FIELD_NUMBER: _ClassVar[int]
    name: str
    next_run_at: _timestamp_pb2.Timestamp
    def __init__(self, name: _Optional[str] = ..., next_run_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class UnregisterCronRequest(_message.Message):
    __slots__ = ("name",)
    NAME_FIELD_NUMBER: _ClassVar[int]
    name: str
    def __init__(self, name: _Optional[str] = ...) -> None: ...

class UnregisterCronResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListCronRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListCronResponse(_message.Message):
    __slots__ = ("entries",)
    ENTRIES_FIELD_NUMBER: _ClassVar[int]
    entries: _containers.RepeatedCompositeFieldContainer[CronEntry]
    def __init__(self, entries: _Optional[_Iterable[_Union[CronEntry, _Mapping]]] = ...) -> None: ...

class CronEntry(_message.Message):
    __slots__ = ("name", "cron", "timezone", "type", "args", "options", "next_run_at", "last_run_at")
    NAME_FIELD_NUMBER: _ClassVar[int]
    CRON_FIELD_NUMBER: _ClassVar[int]
    TIMEZONE_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    NEXT_RUN_AT_FIELD_NUMBER: _ClassVar[int]
    LAST_RUN_AT_FIELD_NUMBER: _ClassVar[int]
    name: str
    cron: str
    timezone: str
    type: str
    args: _containers.RepeatedCompositeFieldContainer[_struct_pb2.Value]
    options: _job_pb2.EnqueueOptions
    next_run_at: _timestamp_pb2.Timestamp
    last_run_at: _timestamp_pb2.Timestamp
    def __init__(self, name: _Optional[str] = ..., cron: _Optional[str] = ..., timezone: _Optional[str] = ..., type: _Optional[str] = ..., args: _Optional[_Iterable[_Union[_struct_pb2.Value, _Mapping]]] = ..., options: _Optional[_Union[_job_pb2.EnqueueOptions, _Mapping]] = ..., next_run_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., last_run_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class SaveCheckpointRequest(_message.Message):
    __slots__ = ("job_id", "state")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    state: _struct_pb2.Struct
    def __init__(self, job_id: _Optional[str] = ..., state: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ...) -> None: ...

class SaveCheckpointResponse(_message.Message):
    __slots__ = ("sequence",)
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    sequence: int
    def __init__(self, sequence: _Optional[int] = ...) -> None: ...

class GetCheckpointRequest(_message.Message):
    __slots__ = ("job_id",)
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    def __init__(self, job_id: _Optional[str] = ...) -> None: ...

class GetCheckpointResponse(_message.Message):
    __slots__ = ("job_id", "state", "sequence", "saved_at")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    SEQUENCE_FIELD_NUMBER: _ClassVar[int]
    SAVED_AT_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    state: _struct_pb2.Struct
    sequence: int
    saved_at: _timestamp_pb2.Timestamp
    def __init__(self, job_id: _Optional[str] = ..., state: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., sequence: _Optional[int] = ..., saved_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class DeleteCheckpointRequest(_message.Message):
    __slots__ = ("job_id",)
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    def __init__(self, job_id: _Optional[str] = ...) -> None: ...

class DeleteCheckpointResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
