"""Backward-compatible analytics facade.

New code should import the domain-specific service module. Keeping this facade
avoids breaking existing API and dashboard integrations during the split.
"""

from aihr.services.analytics_effectiveness import get_effectiveness
from aihr.services.analytics_ml import get_prediction_insights
from aihr.services.analytics_monitoring import get_monitoring
from aihr.services.analytics_overview import get_filter_options, get_funnel, get_overview
from aihr.services.analytics_quality import get_data_quality

__all__ = [
    "get_data_quality",
    "get_effectiveness",
    "get_filter_options",
    "get_funnel",
    "get_monitoring",
    "get_overview",
    "get_prediction_insights",
]
