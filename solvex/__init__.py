"""Solvex — Python client for the Solvex captcha solving API.

Supports FunCaptcha (Arkose Labs) and the four AmazonAws* task types:
``AmazonAwsTask`` (full WAF chain), ``AmazonAwsTaskInvisible`` (PoW only),
``AmazonAwsTaskImage`` (image grid only), and ``AmazonAwsClassificationTask``
(standalone image classifier — no WAF context, no proxy).
"""

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
from .models import (
    AmazonAwsClassificationTask,
    AmazonAwsTask,
    AmazonAwsTaskImage,
    AmazonAwsTaskInvisible,
    ClassificationCell,
    ClassificationTopKEntry,
    FunCaptchaTask,
    Proxy,
    TaskResult,
)

__all__ = [
    "SolvexClient",
    "AsyncSolvexClient",
    "FunCaptchaTask",
    "AmazonAwsTask",
    "AmazonAwsTaskInvisible",
    "AmazonAwsTaskImage",
    "AmazonAwsClassificationTask",
    "ClassificationCell",
    "ClassificationTopKEntry",
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

__version__ = "0.2.0"
