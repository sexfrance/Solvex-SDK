"""Exception hierarchy for the Solvex client.

Every exception carries the original antiCaptcha ``errorId`` + ``errorCode``
when one was returned by the server, so callers can handle specific cases
without parsing error strings.
"""

from __future__ import annotations


class SolvexError(Exception):
    """Base class for all Solvex errors."""

    def __init__(
        self,
        message: str,
        *,
        error_id: int | None = None,
        error_code: str | None = None,
    ):
        super().__init__(message)
        self.error_id = error_id
        self.error_code = error_code

    def __repr__(self) -> str:  # pragma: no cover
        if self.error_id is not None:
            return f"{type(self).__name__}(errorId={self.error_id}, {super().__str__()!r})"
        return super().__repr__()


class InvalidKeyError(SolvexError):
    """clientKey is missing, malformed or revoked (errorId=1)."""


class UnsupportedTaskError(SolvexError):
    """Requested task type is not enabled (errorId=2 / 22)."""


class UnsupportedSiteKeyError(SolvexError):
    """``websitePublicKey`` is not in the registered site-key table (errorId=23).

    Solvex only accepts public keys it has verified the surl / location_href /
    referrer for — passing anything else would leave Arkose to suppress the
    token later with no feedback. Contact support to add a new site.
    """


class InsufficientCreditsError(SolvexError):
    """Account balance is too low for the requested task (errorId=10)."""


class TaskNotFoundError(SolvexError):
    """getTaskResult on an unknown taskId (errorId=16)."""


class TaskFailedError(SolvexError):
    """Task was accepted but the solver couldn't produce a valid token.

    Credits are automatically refunded server-side. ``status`` is ``failed``
    or ``timeout``.
    """

    def __init__(self, message: str, *, status: str, **kwargs: object):
        super().__init__(message, **kwargs)  # type: ignore[arg-type]
        self.status = status


class TaskTimeoutError(SolvexError):
    """Client-side polling exceeded the wait budget.

    The task may still complete on the server — poll again later with the
    same taskId, or treat as failed and submit a new one.
    """


class RateLimitedError(SolvexError):
    """Per-key or per-user rate limit hit (errorId=31)."""


_ERROR_MAP: dict[int, type[SolvexError]] = {
    1: InvalidKeyError,
    2: UnsupportedTaskError,
    10: InsufficientCreditsError,
    12: TaskFailedError,
    16: TaskNotFoundError,
    22: UnsupportedTaskError,
    23: UnsupportedSiteKeyError,
    31: RateLimitedError,
    40: TaskTimeoutError,
}


def exception_for(error_id: int, error_code: str | None, description: str | None) -> SolvexError:
    """Map an antiCaptcha errorId to the right exception subclass."""
    cls = _ERROR_MAP.get(error_id, SolvexError)
    msg = description or error_code or f"Solvex error {error_id}"
    if cls is TaskFailedError:
        return TaskFailedError(msg, status="failed", error_id=error_id, error_code=error_code)
    return cls(msg, error_id=error_id, error_code=error_code)
