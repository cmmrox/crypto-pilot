"""Stable errors independent of transport and persistence."""


class Conflict(ValueError):
    """The transition is stale or conflicts with active work."""
