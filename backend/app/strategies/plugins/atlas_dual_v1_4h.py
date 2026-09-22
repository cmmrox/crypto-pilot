"""Discoverable adapter for the shared Atlas 7 Dual four-hour release."""

from strategy_runtime.atlas_dual import AtlasDual

from app.strategies.base import Strategy, register

PLUGIN: Strategy = register(AtlasDual())
