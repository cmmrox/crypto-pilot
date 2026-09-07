"""Discoverable adapter for the shared, immutable refined four-hour release."""

from strategy_runtime.refined_trend_rider import RefinedTrendRider

from app.strategies.base import Strategy, register

PLUGIN: Strategy = register(RefinedTrendRider())
