import datetime

from google.protobuf import struct_pb2 as _struct_pb2
from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Event(_message.Message):
    __slots__ = ("id", "type", "job_id", "job_type", "queue", "timestamp", "data", "workflow_id")
    ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    JOB_TYPE_FIELD_NUMBER: _ClassVar[int]
    QUEUE_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    type: str
    job_id: str
    job_type: str
    queue: str
    timestamp: _timestamp_pb2.Timestamp
    data: _struct_pb2.Struct
    workflow_id: str
    def __init__(self, id: _Optional[str] = ..., type: _Optional[str] = ..., job_id: _Optional[str] = ..., job_type: _Optional[str] = ..., queue: _Optional[str] = ..., timestamp: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., data: _Optional[_Union[_struct_pb2.Struct, _Mapping]] = ..., workflow_id: _Optional[str] = ...) -> None: ...

class StreamEventsRequest(_message.Message):
    __slots__ = ("queues", "event_types", "job_id", "workflow_id")
    QUEUES_FIELD_NUMBER: _ClassVar[int]
    EVENT_TYPES_FIELD_NUMBER: _ClassVar[int]
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    queues: _containers.RepeatedScalarFieldContainer[str]
    event_types: _containers.RepeatedScalarFieldContainer[str]
    job_id: str
    workflow_id: str
    def __init__(self, queues: _Optional[_Iterable[str]] = ..., event_types: _Optional[_Iterable[str]] = ..., job_id: _Optional[str] = ..., workflow_id: _Optional[str] = ...) -> None: ...
