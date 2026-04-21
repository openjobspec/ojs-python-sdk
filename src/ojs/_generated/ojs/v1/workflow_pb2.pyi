import datetime

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

class WorkflowState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WORKFLOW_STATE_UNSPECIFIED: _ClassVar[WorkflowState]
    WORKFLOW_STATE_RUNNING: _ClassVar[WorkflowState]
    WORKFLOW_STATE_COMPLETED: _ClassVar[WorkflowState]
    WORKFLOW_STATE_FAILED: _ClassVar[WorkflowState]
    WORKFLOW_STATE_CANCELLED: _ClassVar[WorkflowState]

class WorkflowStepState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    WORKFLOW_STEP_STATE_UNSPECIFIED: _ClassVar[WorkflowStepState]
    WORKFLOW_STEP_STATE_WAITING: _ClassVar[WorkflowStepState]
    WORKFLOW_STEP_STATE_PENDING: _ClassVar[WorkflowStepState]
    WORKFLOW_STEP_STATE_ACTIVE: _ClassVar[WorkflowStepState]
    WORKFLOW_STEP_STATE_COMPLETED: _ClassVar[WorkflowStepState]
    WORKFLOW_STEP_STATE_FAILED: _ClassVar[WorkflowStepState]
    WORKFLOW_STEP_STATE_CANCELLED: _ClassVar[WorkflowStepState]
WORKFLOW_STATE_UNSPECIFIED: WorkflowState
WORKFLOW_STATE_RUNNING: WorkflowState
WORKFLOW_STATE_COMPLETED: WorkflowState
WORKFLOW_STATE_FAILED: WorkflowState
WORKFLOW_STATE_CANCELLED: WorkflowState
WORKFLOW_STEP_STATE_UNSPECIFIED: WorkflowStepState
WORKFLOW_STEP_STATE_WAITING: WorkflowStepState
WORKFLOW_STEP_STATE_PENDING: WorkflowStepState
WORKFLOW_STEP_STATE_ACTIVE: WorkflowStepState
WORKFLOW_STEP_STATE_COMPLETED: WorkflowStepState
WORKFLOW_STEP_STATE_FAILED: WorkflowStepState
WORKFLOW_STEP_STATE_CANCELLED: WorkflowStepState

class Workflow(_message.Message):
    __slots__ = ("id", "name", "state", "steps", "created_at", "completed_at")
    ID_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    STEPS_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    COMPLETED_AT_FIELD_NUMBER: _ClassVar[int]
    id: str
    name: str
    state: WorkflowState
    steps: _containers.RepeatedCompositeFieldContainer[WorkflowStepStatus]
    created_at: _timestamp_pb2.Timestamp
    completed_at: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[str] = ..., name: _Optional[str] = ..., state: _Optional[_Union[WorkflowState, str]] = ..., steps: _Optional[_Iterable[_Union[WorkflowStepStatus, _Mapping]]] = ..., created_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., completed_at: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class WorkflowStep(_message.Message):
    __slots__ = ("id", "type", "args", "depends_on", "options")
    ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    ARGS_FIELD_NUMBER: _ClassVar[int]
    DEPENDS_ON_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    id: str
    type: str
    args: _containers.RepeatedCompositeFieldContainer[_struct_pb2.Value]
    depends_on: _containers.RepeatedScalarFieldContainer[str]
    options: _job_pb2.EnqueueOptions
    def __init__(self, id: _Optional[str] = ..., type: _Optional[str] = ..., args: _Optional[_Iterable[_Union[_struct_pb2.Value, _Mapping]]] = ..., depends_on: _Optional[_Iterable[str]] = ..., options: _Optional[_Union[_job_pb2.EnqueueOptions, _Mapping]] = ...) -> None: ...

class WorkflowStepStatus(_message.Message):
    __slots__ = ("id", "type", "state", "job_id", "depends_on")
    ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    DEPENDS_ON_FIELD_NUMBER: _ClassVar[int]
    id: str
    type: str
    state: WorkflowStepState
    job_id: str
    depends_on: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, id: _Optional[str] = ..., type: _Optional[str] = ..., state: _Optional[_Union[WorkflowStepState, str]] = ..., job_id: _Optional[str] = ..., depends_on: _Optional[_Iterable[str]] = ...) -> None: ...

class CreateWorkflowRequest(_message.Message):
    __slots__ = ("name", "steps")
    NAME_FIELD_NUMBER: _ClassVar[int]
    STEPS_FIELD_NUMBER: _ClassVar[int]
    name: str
    steps: _containers.RepeatedCompositeFieldContainer[WorkflowStep]
    def __init__(self, name: _Optional[str] = ..., steps: _Optional[_Iterable[_Union[WorkflowStep, _Mapping]]] = ...) -> None: ...

class CreateWorkflowResponse(_message.Message):
    __slots__ = ("workflow",)
    WORKFLOW_FIELD_NUMBER: _ClassVar[int]
    workflow: Workflow
    def __init__(self, workflow: _Optional[_Union[Workflow, _Mapping]] = ...) -> None: ...

class GetWorkflowRequest(_message.Message):
    __slots__ = ("workflow_id",)
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    def __init__(self, workflow_id: _Optional[str] = ...) -> None: ...

class GetWorkflowResponse(_message.Message):
    __slots__ = ("workflow",)
    WORKFLOW_FIELD_NUMBER: _ClassVar[int]
    workflow: Workflow
    def __init__(self, workflow: _Optional[_Union[Workflow, _Mapping]] = ...) -> None: ...

class CancelWorkflowRequest(_message.Message):
    __slots__ = ("workflow_id", "reason")
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    REASON_FIELD_NUMBER: _ClassVar[int]
    workflow_id: str
    reason: str
    def __init__(self, workflow_id: _Optional[str] = ..., reason: _Optional[str] = ...) -> None: ...

class CancelWorkflowResponse(_message.Message):
    __slots__ = ("workflow",)
    WORKFLOW_FIELD_NUMBER: _ClassVar[int]
    workflow: Workflow
    def __init__(self, workflow: _Optional[_Union[Workflow, _Mapping]] = ...) -> None: ...
