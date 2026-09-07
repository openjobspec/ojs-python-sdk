"""Canonical relative endpoints for Agent Substrate operations."""

from __future__ import annotations

from urllib.parse import quote


def agent_endpoint(job_id: str, operation: str) -> str:
    encoded_job_id = quote(job_id, safe="")
    return f"/agents/{encoded_job_id}/{operation}"


__all__ = ["agent_endpoint"]
