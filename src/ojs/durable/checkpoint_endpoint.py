"""Relative endpoint construction for durable checkpoints."""

from __future__ import annotations

from urllib.parse import quote


def checkpoint_path(job_id: str) -> str:
    return f"/checkpoints/{quote(job_id, safe='')}"


def resume_path(job_id: str) -> str:
    return f"{checkpoint_path(job_id)}/resume"


__all__ = ["checkpoint_path", "resume_path"]
