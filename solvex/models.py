"""Data models used by the Solvex client."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ProxyType = Literal["http", "https", "socks4", "socks5"]


@dataclass(slots=True)
class Proxy:
    """Proxy used to route the solver's browser context."""

    type: ProxyType
    address: str
    port: int
    login: str | None = None
    password: str | None = None

    @classmethod
    def from_url(cls, url: str) -> "Proxy":
        """Parse ``[scheme://][user:pass@]host:port`` into a Proxy."""
        from urllib.parse import urlparse

        u = urlparse(url if "://" in url else f"http://{url}")
        scheme = (u.scheme or "http").lower()
        if scheme not in ("http", "https", "socks4", "socks5"):
            raise ValueError(f"Unsupported proxy scheme: {scheme!r}")
        if not u.hostname or not u.port:
            raise ValueError(f"Proxy URL missing host or port: {url!r}")
        return cls(
            type=scheme,  # type: ignore[arg-type]
            address=u.hostname,
            port=u.port,
            login=u.username,
            password=u.password,
        )


@dataclass(slots=True)
class FunCaptchaTask:
    """A FunCaptcha task ready to be submitted.

    ``proxy`` is required — Solvex does not run proxyless solves.
    """

    website_url: str
    website_public_key: str
    proxy: Proxy
    cookies: str                      # Cookie header from the session that emitted the blob (required)
    data: str | None = None           # Arkose dataExchangeBlob string
    user_agent: str | None = None     # Safari UA override — must be macOS Safari if provided
    use_http3: bool | None = None     # None = server default (enabled)
    solve_pow: bool | None = None     # None = server default (off)
    browser: str | None = None        # "safari" / "auto" / specific profile name

    def to_api_payload(self) -> dict[str, Any]:
        """Shape for the ``task`` field of createTask."""
        payload: dict[str, Any] = {
            "type": "FunCaptchaTask",
            "websiteURL": self.website_url,
            "websitePublicKey": self.website_public_key,
            "proxyType": self.proxy.type,
            "proxyAddress": self.proxy.address,
            "proxyPort": self.proxy.port,
        }
        if self.proxy.login is not None:
            payload["proxyLogin"] = self.proxy.login
        if self.proxy.password is not None:
            payload["proxyPassword"] = self.proxy.password
        if self.data is not None:
            payload["data"] = self.data
        payload["cookies"] = self.cookies
        if self.user_agent is not None:
            payload["userAgent"] = self.user_agent
        if self.use_http3 is not None:
            payload["useHttp3"] = self.use_http3
        if self.solve_pow is not None:
            payload["solvePow"] = self.solve_pow
        if self.browser is not None:
            payload["browser"] = self.browser
        return payload


@dataclass(slots=True)
class TaskResult:
    """Solved FunCaptcha result returned by getTaskResult."""

    task_id: str
    status: Literal["ready"]
    token: str
    cost_usd: float
    create_time: int | None = None
    end_time: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def solve_seconds(self) -> float | None:
        if self.create_time is None or self.end_time is None:
            return None
        return max(0, self.end_time - self.create_time)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
