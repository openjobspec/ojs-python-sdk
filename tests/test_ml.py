"""Tests for the OJS ML/AI Resource Extension."""

from __future__ import annotations

from ojs.ml import (
    GPU_NVIDIA_A100,
    GPU_NVIDIA_H100,
    GPU_NVIDIA_T4,
    GPU_NVIDIA_L4,
    GPU_NVIDIA_V100,
    GPU_AMD_MI250,
    GPU_AMD_MI300X,
    GPURequirements,
    CPURequirements,
    ResourceRequirements,
    ModelReference,
    CheckpointConfig,
    PreemptionConfig,
    with_gpu,
    with_model,
    with_resources,
    with_checkpoint,
    with_preemption,
    merge_ml_meta,
)


class TestGPUConstants:
    def test_gpu_type_values(self) -> None:
        assert GPU_NVIDIA_A100 == "nvidia-a100"
        assert GPU_NVIDIA_H100 == "nvidia-h100"
        assert GPU_NVIDIA_T4 == "nvidia-t4"
        assert GPU_NVIDIA_L4 == "nvidia-l4"
        assert GPU_NVIDIA_V100 == "nvidia-v100"
        assert GPU_AMD_MI250 == "amd-mi250"
        assert GPU_AMD_MI300X == "amd-mi300x"


class TestGPURequirements:
    def test_defaults(self) -> None:
        req = GPURequirements()
        assert req.count == 0
        assert req.type is None
        assert req.memory_gb is None

    def test_with_values(self) -> None:
        req = GPURequirements(type="nvidia-a100", count=2, memory_gb=80)
        assert req.type == "nvidia-a100"
        assert req.count == 2
        assert req.memory_gb == 80

    def test_to_dict(self) -> None:
        req = GPURequirements(type="nvidia-a100", count=4, memory_gb=40)
        d = req.to_dict()
        assert d["count"] == 4
        assert d["type"] == "nvidia-a100"
        assert d["memory_gb"] == 40

    def test_to_dict_minimal(self) -> None:
        req = GPURequirements(count=1)
        d = req.to_dict()
        assert d == {"count": 1}
        assert "type" not in d
        assert "memory_gb" not in d

    def test_frozen(self) -> None:
        req = GPURequirements(count=1)
        try:
            req.count = 2  # type: ignore[misc]
            assert False, "should be frozen"
        except AttributeError:
            pass


class TestCPURequirements:
    def test_defaults(self) -> None:
        req = CPURequirements()
        assert req.cores == 0

    def test_to_dict(self) -> None:
        req = CPURequirements(cores=8)
        assert req.to_dict() == {"cores": 8}


class TestResourceRequirements:
    def test_defaults(self) -> None:
        req = ResourceRequirements()
        assert req.gpu is None
        assert req.cpu is None
        assert req.memory_gb is None
        assert req.storage_gb is None

    def test_full_resource_spec(self) -> None:
        req = ResourceRequirements(
            gpu=GPURequirements(type="nvidia-a100", count=2, memory_gb=80),
            cpu=CPURequirements(cores=16),
            memory_gb=256,
            storage_gb=1000,
        )
        d = req.to_dict()
        assert d["gpu"]["type"] == "nvidia-a100"
        assert d["gpu"]["count"] == 2
        assert d["gpu"]["memory_gb"] == 80
        assert d["cpu"]["cores"] == 16
        assert d["memory_gb"] == 256
        assert d["storage_gb"] == 1000

    def test_to_dict_omits_none(self) -> None:
        req = ResourceRequirements()
        d = req.to_dict()
        assert "gpu" not in d
        assert "cpu" not in d
        assert "memory_gb" not in d
        assert "storage_gb" not in d


class TestModelReference:
    def test_defaults(self) -> None:
        ref = ModelReference()
        assert ref.name == ""
        assert ref.version is None
        assert ref.registry is None
        assert ref.checksum is None

    def test_full_model(self) -> None:
        ref = ModelReference(
            name="llama-3.1-70b",
            version="v2.1",
            registry="huggingface",
            checksum="sha256:abc123",
        )
        d = ref.to_dict()
        assert d["name"] == "llama-3.1-70b"
        assert d["version"] == "v2.1"
        assert d["registry"] == "huggingface"
        assert d["checksum"] == "sha256:abc123"

    def test_to_dict_minimal(self) -> None:
        ref = ModelReference(name="bert-base")
        d = ref.to_dict()
        assert d == {"name": "bert-base"}
        assert "version" not in d


class TestCheckpointConfig:
    def test_defaults(self) -> None:
        cfg = CheckpointConfig()
        assert cfg.enabled is False
        assert cfg.interval_s is None
        assert cfg.storage_uri is None
        assert cfg.max_checkpoints is None

    def test_full_config(self) -> None:
        cfg = CheckpointConfig(
            enabled=True,
            interval_s=300,
            storage_uri="s3://bucket/checkpoints/",
            max_checkpoints=5,
        )
        d = cfg.to_dict()
        assert d["enabled"] is True
        assert d["interval_s"] == 300
        assert d["storage_uri"] == "s3://bucket/checkpoints/"
        assert d["max_checkpoints"] == 5

    def test_to_dict_minimal(self) -> None:
        cfg = CheckpointConfig(enabled=False)
        d = cfg.to_dict()
        assert d == {"enabled": False}


class TestPreemptionConfig:
    def test_defaults(self) -> None:
        cfg = PreemptionConfig()
        assert cfg.preemptible is False
        assert cfg.grace_period_s is None
        assert cfg.checkpoint_on_preempt is None

    def test_full_config(self) -> None:
        cfg = PreemptionConfig(
            preemptible=True,
            grace_period_s=60,
            checkpoint_on_preempt=True,
        )
        d = cfg.to_dict()
        assert d["preemptible"] is True
        assert d["grace_period_s"] == 60
        assert d["checkpoint_on_preempt"] is True


class TestWithGPU:
    def test_basic_gpu(self) -> None:
        meta = with_gpu(GPU_NVIDIA_A100, count=2, memory_gb=80)
        assert "resources" in meta
        gpu = meta["resources"]["gpu"]
        assert gpu["type"] == "nvidia-a100"
        assert gpu["count"] == 2
        assert gpu["memory_gb"] == 80

    def test_gpu_without_memory(self) -> None:
        meta = with_gpu(GPU_NVIDIA_T4, count=1)
        gpu = meta["resources"]["gpu"]
        assert gpu["type"] == "nvidia-t4"
        assert gpu["count"] == 1


class TestWithModel:
    def test_model_reference(self) -> None:
        meta = with_model(
            ModelReference(
                name="resnet50",
                version="1.0.0",
                registry="huggingface",
                checksum="sha256:abc123",
            )
        )
        assert meta["model"]["name"] == "resnet50"
        assert meta["model"]["version"] == "1.0.0"
        assert meta["model"]["registry"] == "huggingface"
        assert meta["model"]["checksum"] == "sha256:abc123"


class TestWithResources:
    def test_full_resources(self) -> None:
        meta = with_resources(
            ResourceRequirements(
                gpu=GPURequirements(type="nvidia-h100", count=8, memory_gb=80),
                cpu=CPURequirements(cores=32),
                memory_gb=512,
                storage_gb=2000,
            )
        )
        assert meta["resources"]["gpu"]["type"] == "nvidia-h100"
        assert meta["resources"]["gpu"]["count"] == 8
        assert meta["resources"]["cpu"]["cores"] == 32
        assert meta["resources"]["memory_gb"] == 512
        assert meta["resources"]["storage_gb"] == 2000


class TestWithCheckpoint:
    def test_checkpoint_config(self) -> None:
        meta = with_checkpoint(
            CheckpointConfig(
                enabled=True,
                interval_s=600,
                storage_uri="s3://bucket/ckpts/",
                max_checkpoints=3,
            )
        )
        assert meta["checkpoint"]["enabled"] is True
        assert meta["checkpoint"]["interval_s"] == 600
        assert meta["checkpoint"]["storage_uri"] == "s3://bucket/ckpts/"


class TestWithPreemption:
    def test_preemption_config(self) -> None:
        meta = with_preemption(
            PreemptionConfig(
                preemptible=True,
                grace_period_s=30,
                checkpoint_on_preempt=True,
            )
        )
        assert meta["preemption"]["preemptible"] is True
        assert meta["preemption"]["grace_period_s"] == 30
        assert meta["preemption"]["checkpoint_on_preempt"] is True


class TestMergeMLMeta:
    def test_merge_multiple_parts(self) -> None:
        meta = merge_ml_meta(
            with_gpu(GPU_NVIDIA_A100, count=2, memory_gb=80),
            with_model(ModelReference(name="resnet50", version="1.0.0")),
            with_checkpoint(CheckpointConfig(enabled=True, interval_s=300)),
        )
        assert "resources" in meta
        assert "model" in meta
        assert "checkpoint" in meta

    def test_merge_empty(self) -> None:
        meta = merge_ml_meta()
        assert meta == {}

    def test_merge_single(self) -> None:
        meta = merge_ml_meta(with_gpu(GPU_NVIDIA_T4, count=1))
        assert "resources" in meta
        assert meta["resources"]["gpu"]["type"] == "nvidia-t4"
