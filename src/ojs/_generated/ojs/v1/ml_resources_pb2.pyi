from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class AcceleratorType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ACCELERATOR_TYPE_UNSPECIFIED: _ClassVar[AcceleratorType]
    ACCELERATOR_TYPE_CPU: _ClassVar[AcceleratorType]
    ACCELERATOR_TYPE_GPU: _ClassVar[AcceleratorType]
    ACCELERATOR_TYPE_TPU: _ClassVar[AcceleratorType]
    ACCELERATOR_TYPE_FPGA: _ClassVar[AcceleratorType]

class GPUInterconnect(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    GPU_INTERCONNECT_UNSPECIFIED: _ClassVar[GPUInterconnect]
    GPU_INTERCONNECT_ANY: _ClassVar[GPUInterconnect]
    GPU_INTERCONNECT_PCIE: _ClassVar[GPUInterconnect]
    GPU_INTERCONNECT_NVLINK: _ClassVar[GPUInterconnect]

class TPUType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    TPU_TYPE_UNSPECIFIED: _ClassVar[TPUType]
    TPU_TYPE_V4: _ClassVar[TPUType]
    TPU_TYPE_V5E: _ClassVar[TPUType]
    TPU_TYPE_V5P: _ClassVar[TPUType]
    TPU_TYPE_V6E: _ClassVar[TPUType]

class ModelProvider(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MODEL_PROVIDER_UNSPECIFIED: _ClassVar[ModelProvider]
    MODEL_PROVIDER_OPENAI: _ClassVar[ModelProvider]
    MODEL_PROVIDER_ANTHROPIC: _ClassVar[ModelProvider]
    MODEL_PROVIDER_GOOGLE: _ClassVar[ModelProvider]
    MODEL_PROVIDER_HUGGINGFACE: _ClassVar[ModelProvider]
    MODEL_PROVIDER_REPLICATE: _ClassVar[ModelProvider]
    MODEL_PROVIDER_LOCAL: _ClassVar[ModelProvider]
    MODEL_PROVIDER_CUSTOM: _ClassVar[ModelProvider]

class ModelFormat(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    MODEL_FORMAT_UNSPECIFIED: _ClassVar[ModelFormat]
    MODEL_FORMAT_SAFETENSORS: _ClassVar[ModelFormat]
    MODEL_FORMAT_GGUF: _ClassVar[ModelFormat]
    MODEL_FORMAT_ONNX: _ClassVar[ModelFormat]
    MODEL_FORMAT_TORCHSCRIPT: _ClassVar[ModelFormat]
    MODEL_FORMAT_SAVEDMODEL: _ClassVar[ModelFormat]
    MODEL_FORMAT_CUSTOM: _ClassVar[ModelFormat]

class PriorityClass(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PRIORITY_CLASS_UNSPECIFIED: _ClassVar[PriorityClass]
    PRIORITY_CLASS_SPOT: _ClassVar[PriorityClass]
    PRIORITY_CLASS_ON_DEMAND: _ClassVar[PriorityClass]
    PRIORITY_CLASS_RESERVED: _ClassVar[PriorityClass]

class MLRuntime(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    ML_RUNTIME_UNSPECIFIED: _ClassVar[MLRuntime]
    ML_RUNTIME_PYTORCH: _ClassVar[MLRuntime]
    ML_RUNTIME_TENSORFLOW: _ClassVar[MLRuntime]
    ML_RUNTIME_ONNX: _ClassVar[MLRuntime]
    ML_RUNTIME_TRITON: _ClassVar[MLRuntime]
    ML_RUNTIME_VLLM: _ClassVar[MLRuntime]
    ML_RUNTIME_TGI: _ClassVar[MLRuntime]
    ML_RUNTIME_CUSTOM: _ClassVar[MLRuntime]

class Precision(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    PRECISION_UNSPECIFIED: _ClassVar[Precision]
    PRECISION_FP32: _ClassVar[Precision]
    PRECISION_FP16: _ClassVar[Precision]
    PRECISION_BF16: _ClassVar[Precision]
    PRECISION_FP8: _ClassVar[Precision]
    PRECISION_INT8: _ClassVar[Precision]
    PRECISION_INT4: _ClassVar[Precision]

class DistributedStrategy(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DISTRIBUTED_STRATEGY_UNSPECIFIED: _ClassVar[DistributedStrategy]
    DISTRIBUTED_STRATEGY_NONE: _ClassVar[DistributedStrategy]
    DISTRIBUTED_STRATEGY_DATA_PARALLEL: _ClassVar[DistributedStrategy]
    DISTRIBUTED_STRATEGY_TENSOR_PARALLEL: _ClassVar[DistributedStrategy]
    DISTRIBUTED_STRATEGY_PIPELINE_PARALLEL: _ClassVar[DistributedStrategy]
    DISTRIBUTED_STRATEGY_FSDP: _ClassVar[DistributedStrategy]
    DISTRIBUTED_STRATEGY_DEEPSPEED: _ClassVar[DistributedStrategy]

class AffinityOperator(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    AFFINITY_OPERATOR_UNSPECIFIED: _ClassVar[AffinityOperator]
    AFFINITY_OPERATOR_IN: _ClassVar[AffinityOperator]
    AFFINITY_OPERATOR_NOT_IN: _ClassVar[AffinityOperator]
    AFFINITY_OPERATOR_EXISTS: _ClassVar[AffinityOperator]
    AFFINITY_OPERATOR_DOES_NOT_EXIST: _ClassVar[AffinityOperator]
    AFFINITY_OPERATOR_GT: _ClassVar[AffinityOperator]
    AFFINITY_OPERATOR_GTE: _ClassVar[AffinityOperator]
    AFFINITY_OPERATOR_LT: _ClassVar[AffinityOperator]
    AFFINITY_OPERATOR_LTE: _ClassVar[AffinityOperator]
ACCELERATOR_TYPE_UNSPECIFIED: AcceleratorType
ACCELERATOR_TYPE_CPU: AcceleratorType
ACCELERATOR_TYPE_GPU: AcceleratorType
ACCELERATOR_TYPE_TPU: AcceleratorType
ACCELERATOR_TYPE_FPGA: AcceleratorType
GPU_INTERCONNECT_UNSPECIFIED: GPUInterconnect
GPU_INTERCONNECT_ANY: GPUInterconnect
GPU_INTERCONNECT_PCIE: GPUInterconnect
GPU_INTERCONNECT_NVLINK: GPUInterconnect
TPU_TYPE_UNSPECIFIED: TPUType
TPU_TYPE_V4: TPUType
TPU_TYPE_V5E: TPUType
TPU_TYPE_V5P: TPUType
TPU_TYPE_V6E: TPUType
MODEL_PROVIDER_UNSPECIFIED: ModelProvider
MODEL_PROVIDER_OPENAI: ModelProvider
MODEL_PROVIDER_ANTHROPIC: ModelProvider
MODEL_PROVIDER_GOOGLE: ModelProvider
MODEL_PROVIDER_HUGGINGFACE: ModelProvider
MODEL_PROVIDER_REPLICATE: ModelProvider
MODEL_PROVIDER_LOCAL: ModelProvider
MODEL_PROVIDER_CUSTOM: ModelProvider
MODEL_FORMAT_UNSPECIFIED: ModelFormat
MODEL_FORMAT_SAFETENSORS: ModelFormat
MODEL_FORMAT_GGUF: ModelFormat
MODEL_FORMAT_ONNX: ModelFormat
MODEL_FORMAT_TORCHSCRIPT: ModelFormat
MODEL_FORMAT_SAVEDMODEL: ModelFormat
MODEL_FORMAT_CUSTOM: ModelFormat
PRIORITY_CLASS_UNSPECIFIED: PriorityClass
PRIORITY_CLASS_SPOT: PriorityClass
PRIORITY_CLASS_ON_DEMAND: PriorityClass
PRIORITY_CLASS_RESERVED: PriorityClass
ML_RUNTIME_UNSPECIFIED: MLRuntime
ML_RUNTIME_PYTORCH: MLRuntime
ML_RUNTIME_TENSORFLOW: MLRuntime
ML_RUNTIME_ONNX: MLRuntime
ML_RUNTIME_TRITON: MLRuntime
ML_RUNTIME_VLLM: MLRuntime
ML_RUNTIME_TGI: MLRuntime
ML_RUNTIME_CUSTOM: MLRuntime
PRECISION_UNSPECIFIED: Precision
PRECISION_FP32: Precision
PRECISION_FP16: Precision
PRECISION_BF16: Precision
PRECISION_FP8: Precision
PRECISION_INT8: Precision
PRECISION_INT4: Precision
DISTRIBUTED_STRATEGY_UNSPECIFIED: DistributedStrategy
DISTRIBUTED_STRATEGY_NONE: DistributedStrategy
DISTRIBUTED_STRATEGY_DATA_PARALLEL: DistributedStrategy
DISTRIBUTED_STRATEGY_TENSOR_PARALLEL: DistributedStrategy
DISTRIBUTED_STRATEGY_PIPELINE_PARALLEL: DistributedStrategy
DISTRIBUTED_STRATEGY_FSDP: DistributedStrategy
DISTRIBUTED_STRATEGY_DEEPSPEED: DistributedStrategy
AFFINITY_OPERATOR_UNSPECIFIED: AffinityOperator
AFFINITY_OPERATOR_IN: AffinityOperator
AFFINITY_OPERATOR_NOT_IN: AffinityOperator
AFFINITY_OPERATOR_EXISTS: AffinityOperator
AFFINITY_OPERATOR_DOES_NOT_EXIST: AffinityOperator
AFFINITY_OPERATOR_GT: AffinityOperator
AFFINITY_OPERATOR_GTE: AffinityOperator
AFFINITY_OPERATOR_LT: AffinityOperator
AFFINITY_OPERATOR_LTE: AffinityOperator

class MLResourceRequirements(_message.Message):
    __slots__ = ("accelerator", "gpu", "tpu", "cpu_cores", "memory_gb", "storage_gb", "shm_size_gb")
    ACCELERATOR_FIELD_NUMBER: _ClassVar[int]
    GPU_FIELD_NUMBER: _ClassVar[int]
    TPU_FIELD_NUMBER: _ClassVar[int]
    CPU_CORES_FIELD_NUMBER: _ClassVar[int]
    MEMORY_GB_FIELD_NUMBER: _ClassVar[int]
    STORAGE_GB_FIELD_NUMBER: _ClassVar[int]
    SHM_SIZE_GB_FIELD_NUMBER: _ClassVar[int]
    accelerator: AcceleratorType
    gpu: GPURequirements
    tpu: TPURequirements
    cpu_cores: int
    memory_gb: float
    storage_gb: float
    shm_size_gb: float
    def __init__(self, accelerator: _Optional[_Union[AcceleratorType, str]] = ..., gpu: _Optional[_Union[GPURequirements, _Mapping]] = ..., tpu: _Optional[_Union[TPURequirements, _Mapping]] = ..., cpu_cores: _Optional[int] = ..., memory_gb: _Optional[float] = ..., storage_gb: _Optional[float] = ..., shm_size_gb: _Optional[float] = ...) -> None: ...

class GPURequirements(_message.Message):
    __slots__ = ("type", "count", "memory_gb", "compute_capability", "interconnect")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    MEMORY_GB_FIELD_NUMBER: _ClassVar[int]
    COMPUTE_CAPABILITY_FIELD_NUMBER: _ClassVar[int]
    INTERCONNECT_FIELD_NUMBER: _ClassVar[int]
    type: str
    count: int
    memory_gb: float
    compute_capability: str
    interconnect: GPUInterconnect
    def __init__(self, type: _Optional[str] = ..., count: _Optional[int] = ..., memory_gb: _Optional[float] = ..., compute_capability: _Optional[str] = ..., interconnect: _Optional[_Union[GPUInterconnect, str]] = ...) -> None: ...

class TPURequirements(_message.Message):
    __slots__ = ("type", "topology", "chip_count")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    TOPOLOGY_FIELD_NUMBER: _ClassVar[int]
    CHIP_COUNT_FIELD_NUMBER: _ClassVar[int]
    type: TPUType
    topology: str
    chip_count: int
    def __init__(self, type: _Optional[_Union[TPUType, str]] = ..., topology: _Optional[str] = ..., chip_count: _Optional[int] = ...) -> None: ...

class MLModelInfo(_message.Message):
    __slots__ = ("model_id", "model_version", "provider", "checksum", "format")
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    PROVIDER_FIELD_NUMBER: _ClassVar[int]
    CHECKSUM_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    model_id: str
    model_version: str
    provider: ModelProvider
    checksum: str
    format: ModelFormat
    def __init__(self, model_id: _Optional[str] = ..., model_version: _Optional[str] = ..., provider: _Optional[_Union[ModelProvider, str]] = ..., checksum: _Optional[str] = ..., format: _Optional[_Union[ModelFormat, str]] = ...) -> None: ...

class MLComputeConstraints(_message.Message):
    __slots__ = ("max_tokens", "max_batch_size", "timeout_seconds", "priority_class", "runtime", "precision", "distributed_strategy")
    MAX_TOKENS_FIELD_NUMBER: _ClassVar[int]
    MAX_BATCH_SIZE_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_SECONDS_FIELD_NUMBER: _ClassVar[int]
    PRIORITY_CLASS_FIELD_NUMBER: _ClassVar[int]
    RUNTIME_FIELD_NUMBER: _ClassVar[int]
    PRECISION_FIELD_NUMBER: _ClassVar[int]
    DISTRIBUTED_STRATEGY_FIELD_NUMBER: _ClassVar[int]
    max_tokens: int
    max_batch_size: int
    timeout_seconds: int
    priority_class: PriorityClass
    runtime: MLRuntime
    precision: Precision
    distributed_strategy: DistributedStrategy
    def __init__(self, max_tokens: _Optional[int] = ..., max_batch_size: _Optional[int] = ..., timeout_seconds: _Optional[int] = ..., priority_class: _Optional[_Union[PriorityClass, str]] = ..., runtime: _Optional[_Union[MLRuntime, str]] = ..., precision: _Optional[_Union[Precision, str]] = ..., distributed_strategy: _Optional[_Union[DistributedStrategy, str]] = ...) -> None: ...

class CheckpointConfig(_message.Message):
    __slots__ = ("enabled", "interval_seconds", "storage_uri", "max_checkpoints")
    ENABLED_FIELD_NUMBER: _ClassVar[int]
    INTERVAL_SECONDS_FIELD_NUMBER: _ClassVar[int]
    STORAGE_URI_FIELD_NUMBER: _ClassVar[int]
    MAX_CHECKPOINTS_FIELD_NUMBER: _ClassVar[int]
    enabled: bool
    interval_seconds: int
    storage_uri: str
    max_checkpoints: int
    def __init__(self, enabled: _Optional[bool] = ..., interval_seconds: _Optional[int] = ..., storage_uri: _Optional[str] = ..., max_checkpoints: _Optional[int] = ...) -> None: ...

class PreemptionPolicy(_message.Message):
    __slots__ = ("preemptible", "grace_period_seconds", "checkpoint_on_preempt")
    PREEMPTIBLE_FIELD_NUMBER: _ClassVar[int]
    GRACE_PERIOD_SECONDS_FIELD_NUMBER: _ClassVar[int]
    CHECKPOINT_ON_PREEMPT_FIELD_NUMBER: _ClassVar[int]
    preemptible: bool
    grace_period_seconds: int
    checkpoint_on_preempt: bool
    def __init__(self, preemptible: _Optional[bool] = ..., grace_period_seconds: _Optional[int] = ..., checkpoint_on_preempt: _Optional[bool] = ...) -> None: ...

class NodeSelector(_message.Message):
    __slots__ = ("labels",)
    class LabelsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    LABELS_FIELD_NUMBER: _ClassVar[int]
    labels: _containers.ScalarMap[str, str]
    def __init__(self, labels: _Optional[_Mapping[str, str]] = ...) -> None: ...

class AffinityRule(_message.Message):
    __slots__ = ("key", "operator", "values")
    KEY_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    key: str
    operator: AffinityOperator
    values: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, key: _Optional[str] = ..., operator: _Optional[_Union[AffinityOperator, str]] = ..., values: _Optional[_Iterable[str]] = ...) -> None: ...

class WeightedAffinityRule(_message.Message):
    __slots__ = ("key", "operator", "values", "weight")
    KEY_FIELD_NUMBER: _ClassVar[int]
    OPERATOR_FIELD_NUMBER: _ClassVar[int]
    VALUES_FIELD_NUMBER: _ClassVar[int]
    WEIGHT_FIELD_NUMBER: _ClassVar[int]
    key: str
    operator: AffinityOperator
    values: _containers.RepeatedScalarFieldContainer[str]
    weight: int
    def __init__(self, key: _Optional[str] = ..., operator: _Optional[_Union[AffinityOperator, str]] = ..., values: _Optional[_Iterable[str]] = ..., weight: _Optional[int] = ...) -> None: ...

class Affinity(_message.Message):
    __slots__ = ("required", "preferred")
    REQUIRED_FIELD_NUMBER: _ClassVar[int]
    PREFERRED_FIELD_NUMBER: _ClassVar[int]
    required: _containers.RepeatedCompositeFieldContainer[AffinityRule]
    preferred: _containers.RepeatedCompositeFieldContainer[WeightedAffinityRule]
    def __init__(self, required: _Optional[_Iterable[_Union[AffinityRule, _Mapping]]] = ..., preferred: _Optional[_Iterable[_Union[WeightedAffinityRule, _Mapping]]] = ...) -> None: ...

class ResourceReservation(_message.Message):
    __slots__ = ("reservation_id", "timeout_seconds")
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    TIMEOUT_SECONDS_FIELD_NUMBER: _ClassVar[int]
    reservation_id: str
    timeout_seconds: int
    def __init__(self, reservation_id: _Optional[str] = ..., timeout_seconds: _Optional[int] = ...) -> None: ...

class WorkerMLCapabilities(_message.Message):
    __slots__ = ("accelerator", "gpu", "tpu", "cpu_cores", "memory_gb", "storage_gb", "shm_size_gb", "models_loaded", "runtimes", "labels")
    class LabelsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    ACCELERATOR_FIELD_NUMBER: _ClassVar[int]
    GPU_FIELD_NUMBER: _ClassVar[int]
    TPU_FIELD_NUMBER: _ClassVar[int]
    CPU_CORES_FIELD_NUMBER: _ClassVar[int]
    MEMORY_GB_FIELD_NUMBER: _ClassVar[int]
    STORAGE_GB_FIELD_NUMBER: _ClassVar[int]
    SHM_SIZE_GB_FIELD_NUMBER: _ClassVar[int]
    MODELS_LOADED_FIELD_NUMBER: _ClassVar[int]
    RUNTIMES_FIELD_NUMBER: _ClassVar[int]
    LABELS_FIELD_NUMBER: _ClassVar[int]
    accelerator: AcceleratorType
    gpu: WorkerGPUCapability
    tpu: WorkerTPUCapability
    cpu_cores: int
    memory_gb: float
    storage_gb: float
    shm_size_gb: float
    models_loaded: _containers.RepeatedCompositeFieldContainer[LoadedModel]
    runtimes: _containers.RepeatedScalarFieldContainer[MLRuntime]
    labels: _containers.ScalarMap[str, str]
    def __init__(self, accelerator: _Optional[_Union[AcceleratorType, str]] = ..., gpu: _Optional[_Union[WorkerGPUCapability, _Mapping]] = ..., tpu: _Optional[_Union[WorkerTPUCapability, _Mapping]] = ..., cpu_cores: _Optional[int] = ..., memory_gb: _Optional[float] = ..., storage_gb: _Optional[float] = ..., shm_size_gb: _Optional[float] = ..., models_loaded: _Optional[_Iterable[_Union[LoadedModel, _Mapping]]] = ..., runtimes: _Optional[_Iterable[_Union[MLRuntime, str]]] = ..., labels: _Optional[_Mapping[str, str]] = ...) -> None: ...

class WorkerGPUCapability(_message.Message):
    __slots__ = ("type", "count", "memory_gb", "compute_capability", "interconnect")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    COUNT_FIELD_NUMBER: _ClassVar[int]
    MEMORY_GB_FIELD_NUMBER: _ClassVar[int]
    COMPUTE_CAPABILITY_FIELD_NUMBER: _ClassVar[int]
    INTERCONNECT_FIELD_NUMBER: _ClassVar[int]
    type: str
    count: int
    memory_gb: float
    compute_capability: str
    interconnect: GPUInterconnect
    def __init__(self, type: _Optional[str] = ..., count: _Optional[int] = ..., memory_gb: _Optional[float] = ..., compute_capability: _Optional[str] = ..., interconnect: _Optional[_Union[GPUInterconnect, str]] = ...) -> None: ...

class WorkerTPUCapability(_message.Message):
    __slots__ = ("type", "topology", "chip_count")
    TYPE_FIELD_NUMBER: _ClassVar[int]
    TOPOLOGY_FIELD_NUMBER: _ClassVar[int]
    CHIP_COUNT_FIELD_NUMBER: _ClassVar[int]
    type: TPUType
    topology: str
    chip_count: int
    def __init__(self, type: _Optional[_Union[TPUType, str]] = ..., topology: _Optional[str] = ..., chip_count: _Optional[int] = ...) -> None: ...

class LoadedModel(_message.Message):
    __slots__ = ("model_id", "model_version", "format")
    MODEL_ID_FIELD_NUMBER: _ClassVar[int]
    MODEL_VERSION_FIELD_NUMBER: _ClassVar[int]
    FORMAT_FIELD_NUMBER: _ClassVar[int]
    model_id: str
    model_version: str
    format: ModelFormat
    def __init__(self, model_id: _Optional[str] = ..., model_version: _Optional[str] = ..., format: _Optional[_Union[ModelFormat, str]] = ...) -> None: ...

class CheckpointMetadata(_message.Message):
    __slots__ = ("job_id", "epoch", "step", "loss", "storage_key", "created_at", "metadata")
    class MetadataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    EPOCH_FIELD_NUMBER: _ClassVar[int]
    STEP_FIELD_NUMBER: _ClassVar[int]
    LOSS_FIELD_NUMBER: _ClassVar[int]
    STORAGE_KEY_FIELD_NUMBER: _ClassVar[int]
    CREATED_AT_FIELD_NUMBER: _ClassVar[int]
    METADATA_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    epoch: int
    step: int
    loss: float
    storage_key: str
    created_at: str
    metadata: _containers.ScalarMap[str, str]
    def __init__(self, job_id: _Optional[str] = ..., epoch: _Optional[int] = ..., step: _Optional[int] = ..., loss: _Optional[float] = ..., storage_key: _Optional[str] = ..., created_at: _Optional[str] = ..., metadata: _Optional[_Mapping[str, str]] = ...) -> None: ...
