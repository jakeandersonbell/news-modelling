"""Data retrieval clients for Phase 1 source evaluation.

Import the clients directly for use in notebooks and scripts::

    from src.data_retrieval import GdeltClient, CCNewsClient
"""

from .cc_news_parser import (
    CCNewsClient,
    CCNewsError,
    CCNewsIndexError,
    CCNewsRecord,
)
from .gdelt_bigquery import GdeltBigQueryClient, GdeltBigQueryError
from .gdelt_client import GdeltArticle, GdeltClient, GdeltError

__all__ = [
    "GdeltClient",
    "GdeltArticle",
    "GdeltError",
    "GdeltBigQueryClient",
    "GdeltBigQueryError",
    "CCNewsClient",
    "CCNewsRecord",
    "CCNewsError",
    "CCNewsIndexError",
]
