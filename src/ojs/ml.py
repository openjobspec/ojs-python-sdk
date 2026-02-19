"""OJS ML/AI Resource Extension.

Provides types and helpers for declaring GPU, CPU, memory, and storage
requirements on jobs, following the OJS ML Resource Extension Specification.

Resource requirements are stored in the job's ``meta`` field and require
no changes to the core OJS specification.

Usage::

    import ojs
    from ojs.ml import (
        ResourceRequirements,
        GPURequirements,
        ModelReference,
        with_gpu,
        with_model,
        with_resources,
        GPU_NVIDIA_A100,
    )

    job = await client.enqueue(
        "ml.train",
        [{"model": "resnet50", "epochs": 100}],
        meta=with_gpu(GPU_NVIDIA_A100, count=2, memory_gb=80),
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---- GPU Type Constants ----

GPU_NVIDIA_A100: str = "nvidia-a100"
GPU_NVIDIA_H100: str = "nvidia-h100"
GPU_NVIDIA_T4: str = "nvidia-t4"
GPU_NVIDIA_L4: str = "nvidia-l4"
GPU_NVIDIA_V100: str = "nvidia-v100"
GPU_AMD_MI250: str = "amd-mi250"
GPU_AMD_MI300X: str = "amd-mi300x"
GPU_GOOGLE_TPU_V5: str = "google-tpu-v5"


# ---- Data Classes ----


@dataclass(frozen=True)
class GPURequirements:
    """GPU resource requirements.

    Attributes:
        type: GPU model identifier (e.g., ``nvidia-a100``).
        count: Number of GPUs required (default: 0).
        memory_gb: Minimum GPU memory per device in GB.
    """

    count: int = 0
    type: str | None = None
    memory_gb: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"count": self.count}
        if self.type is not None:
            d["type"] = self.type
        if self.memory_gb is not None:
            d["memory_gb"] = self.memory_gb
        return d


@dataclass(frozen=True)
class CPURequirements:
    """CPU resource requirements.

    Attributes:
        cores: Minimum CPU cores required.
    """

    cores: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"cores": self.cores}


@dataclass(frozen=True)
class ResourceRequirements:
    """Compute resource requirements for a job.

    Follows the ``meta.resources`` schema from the OJS ML Resource spec.

    Attributes:
        gpu: GPU resource needs.
        cpu: CPU resource needs.
        memory_gb: Minimum system memory in GB.
        storage_gb: Minimum scratch storage in GB.
    """

    gpu: GPURequirements | None = None
    cpu: CPURequirements | None = None
    memory_gb: float | None = None
    storage_gb: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {}
        if self.gpu is not None:
            d["gpu"] = self.gpu.to_dict()
        if self.cpu is not None:
            d["cpu"] = self.cpu.to_dict()
        if self.memory_gb is not None:
            d["memory_gb"] = self.memory_gb
        if self.storage_gb is not None:
            d["storage_gb"] = self.storage_gb
        return d


@dataclass(frozen=True)
class ModelReference:
    """Reference to an ML model artifact.

    Attributes:
        name: Model name or identifier.
        version: Model version string.
        registry: Model registry (e.g., ``huggingface``).
        checksum: Integrity checksum (e.g., ``sha256:abc123``).
    """

    name: str = ""
    version: str | None = None
    registry: str | None = None
    checksum: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name}
        if self.version is not None:
            d["version"] = self.version
        if self.registry is not None:
            d["registry"] = self.registry
        if self.checksum is not None:
            d["checksum"] = self.checksum
        return d


@dataclass(frozen=True)
class CheckpointConfig:
    """Checkpoint configuration for long-running jobs.

    Attributes:
        enabled: Whether checkpointing is enabled.
        interval_s: Checkpoint interval in seconds.
        storage_uri: URI prefix for checkpoint storage.
        max_checkpoints: Maximum checkpoints to retain (FIFO eviction).
    """

    enabled: bool = False
    interval_s: int | None = None
    storage_uri: str | None = None
    max_checkpoints: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"enabled": self.enabled}
        if self.interval_s is not None:
            d["interval_s"] = self.interval_s
        if self.storage_uri is not None:
            d["storage_uri"] = self.storage_uri
        if self.max_checkpoints is not None:
            d["max_checkpoints"] = self.max_checkpoints
        return d


@dataclass(frozen=True)
class PreemptionConfig:
    """Preemption tolerance configuration.

    Attributes:
        preemptible: Whether the job can be preempted.
        grace_period_s: Seconds of warning before preemption.
        checkpoint_on_preempt: Whether to checkpoint before preemption.
    """

    preemptible: bool = False
    grace_period_s: int | None = None
    checkpoint_on_preempt: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"preemptible": self.preemptible}
        if self.grace_period_s is not None:
            d["grace_period_s"] = self.grace_period_s
        if self.checkpoint_on_preempt is not None:
            d["checkpoint_on_preempt"] = self.checkpoint_on_preempt
        return d


# ---- Helper Functions ----


def with_gpu(
    gpu_type: str,
    count: int = 1,
    memory_gb: float | None = None,
) -> dict[str, Any]:
    """Build a meta dict with GPU resource requirements.

    Returns a dict suitable for passing as the ``meta`` kwarg to
    ``client.enqueue()``, or for merging with other meta dicts.

    Args:
        gpu_type: GPU model identifier constant.
        count: Number of GPUs required.
        memory_gb: Minimum GPU memory per device in GB.
    """
    return with_resources(
        ResourceRequirements(
            gpu=GPURequirements(type=gpu_type, count=count, memory_gb=memory_gb),
        )
    )


def with_model(ref: ModelReference) -> dict[str, Any]:
    """Build a meta dict with a model reference.

    Args:
        ref: The model reference.
    """
    return {"model": ref.to_dict()}


def with_resources(req: ResourceRequirements) -> dict[str, Any]:
    """Build a meta dict with full resource requirements.

    Args:
        req: The resource requirements.
    """
    return {"resources": req.to_dict()}


def with_checkpoint(cfg: CheckpointConfig) -> dict[str, Any]:
    """Build a meta dict with checkpoint configuration.

    Args:
        cfg: The checkpoint configuration.
    """
    return {"checkpoint": cfg.to_dict()}


def with_preemption(cfg: PreemptionConfig) -> dict[str, Any]:
    """Build a meta dict with preemption configuration.

    Args:
        cfg: The preemption configuration.
    """
    return {"preemption": cfg.to_dict()}


def merge_ml_meta(*parts: dict[str, Any]) -> dict[str, Any]:
    """Merge multiple ML meta dicts into one.

    Use this to combine ``with_gpu``, ``with_model``, ``with_checkpoint``, etc.

    Example::

        meta = merge_ml_meta(
            with_gpu(GPU_NVIDIA_A100, count=2, memory_gb=80),
            with_model(ModelReference(name="resnet50", version="1.0.0")),
            with_checkpoint(CheckpointConfig(enabled=True, interval_s=300)),
        )
        await client.enqueue("ml.train", args, meta=meta)
    """
    merged: dict[str, Any] = {}
    for part in parts:
        merged.update(part)
    return merged
