"""Solvex — Python client for the Solvex FunCaptcha solving API."""

from __future__ import annotations

from .client import AsyncSolvexClient, SolvexClient
from .exceptions import (
    SolvexError,
    InvalidKeyError,
    InsufficientCreditsError,
    RateLimitedError,
    TaskFailedError,
    TaskNotFoundError,
    TaskTimeoutError,
    UnsupportedSiteKeyError,
    UnsupportedTaskError,
)
from .models import FunCaptchaTask, Proxy, TaskResult

__all__ = [
    "SolvexClient",
    "AsyncSolvexClient",
    "FunCaptchaTask",
    "Proxy",
    "TaskResult",
    "SolvexError",
    "InvalidKeyError",
    "InsufficientCreditsError",
    "RateLimitedError",
    "TaskFailedError",
    "TaskNotFoundError",
    "TaskTimeoutError",
    "UnsupportedSiteKeyError",
    "UnsupportedTaskError",
]

__version__ = "0.1.0"
