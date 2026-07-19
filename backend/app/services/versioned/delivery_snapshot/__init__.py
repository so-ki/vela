"""Frozen delivery snapshot readers. Historical modules are append-only."""

from app.services.versioned.delivery_snapshot import v1_0

__all__ = ["v1_0"]
