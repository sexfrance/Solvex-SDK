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


# ── AWS WAF task types ─────────────────────────────────────────────────────
#
# All four AmazonAws* tasks share the same JSON schema as FunCaptcha at the
# envelope level (clientKey + task) but use different `type` values and
# different fields.  They're modelled as separate dataclasses so static
# type-checkers catch missing required fields per task type.


@dataclass(slots=True)
class _AmazonAwsBase:
    """Shared serialisation for the three AmazonAws solving tasks (chain /
    invisible / image).  Not meant to be instantiated directly — concrete
    subclasses set ``_task_type`` and override required-field validation
    via the dataclass field defaults.

    ``page_url`` is required by the API for all solving variants.  It is
    the EXACT URL of the page the WAF SDK runs on (e.g. /sign_in, not the
    bare origin) — landing the wrong URL in fp.location bumps WAF
    difficulty noticeably.

    Two equivalent ways to supply gokuProps (only relevant for image
    solves), in priority order:
      1. ``goku_props`` — already-assembled JSON object
      2. ``aws_key`` + ``aws_iv`` + ``aws_context`` — three decomposed
         strings (CapSolver-style); the SDK forwards them and the worker
         assembles them server-side
    """

    website_url: str
    challenge_url: str
    page_url: str
    proxy: Proxy
    locale: str | None = None
    cookies: str | None = None
    aws_api_key: str | None = None
    goku_props: Any | None = None
    # CapSolver-style decomposed gokuProps — pass all three or none.
    aws_key: str | None = None
    aws_iv: str | None = None
    aws_context: str | None = None

    # Override in subclass.  Defined here so to_api_payload can read it.
    _task_type: str = field(default="", init=False, repr=False)

    def _payload(self) -> dict[str, Any]:
        # Quick local validation for the decomposed gokuProps — saves a
        # round trip when the caller pulled only one of the three.
        decomposed = (self.aws_key, self.aws_iv, self.aws_context)
        decomposed_count = sum(1 for v in decomposed if v)
        if 0 < decomposed_count < 3:
            raise ValueError(
                "aws_key / aws_iv / aws_context must be supplied together — "
                "they are the three fields of window.gokuProps = {key, iv, context}."
            )

        payload: dict[str, Any] = {
            "type": self._task_type,
            "websiteURL": self.website_url,
            "challengeURL": self.challenge_url,
            "pageURL": self.page_url,
            "proxyType": self.proxy.type,
            "proxyAddress": self.proxy.address,
            "proxyPort": self.proxy.port,
        }
        if self.proxy.login is not None:
            payload["proxyLogin"] = self.proxy.login
        if self.proxy.password is not None:
            payload["proxyPassword"] = self.proxy.password
        if self.locale is not None:
            payload["locale"] = self.locale
        if self.cookies is not None:
            payload["cookies"] = self.cookies
        if self.aws_api_key is not None:
            payload["awsApiKey"] = self.aws_api_key
        if self.goku_props is not None:
            payload["gokuProps"] = self.goku_props
        if self.aws_key is not None:
            payload["awsKey"] = self.aws_key
            payload["awsIv"] = self.aws_iv
            payload["awsContext"] = self.aws_context
        return payload


@dataclass(slots=True)
class AmazonAwsTask(_AmazonAwsBase):
    """Auto AWS WAF solver — pageURL + proxy is all you need.

    The solver probes ``page_url`` through the supplied proxy itself: if
    AWS WAF returns a 405 (or the body embeds ``window.gokuProps``), it
    auto-falls into the image flow and extracts everything from the
    response.  No 405 → invisible-only token.

    All other 405 artifacts (``aws_api_key``, ``aws_key`` / ``aws_iv`` /
    ``aws_context``, ``cookies``) are optional shortcuts — pass them if
    you already extracted them client-side to skip the probe round-trip;
    otherwise leave them empty and the solver figures it out.

    Check ``TaskResult.image_solved`` to see which path actually ran.
    """

    existing_token: str | None = None

    _task_type: str = field(default="AmazonAwsTask", init=False, repr=False)

    def to_api_payload(self) -> dict[str, Any]:
        payload = self._payload()
        if self.existing_token is not None:
            payload["existingToken"] = self.existing_token
        return payload


@dataclass(slots=True)
class AmazonAwsTaskInvisible(_AmazonAwsBase):
    """PoW-only AWS WAF solve — fastest path, no image inference.

    Cheapest way to mint or refresh an invisible WAF token.  Pass
    ``existing_token`` to refresh an existing one rather than mint fresh.
    """

    existing_token: str | None = None

    _task_type: str = field(default="AmazonAwsTaskInvisible", init=False, repr=False)

    def to_api_payload(self) -> dict[str, Any]:
        payload = self._payload()
        if self.existing_token is not None:
            payload["existingToken"] = self.existing_token
        return payload


@dataclass(slots=True)
class AmazonAwsTaskImage(_AmazonAwsBase):
    """Image-grid-only AWS WAF solve.

    Skips the PoW round-trip; you must already have an invisible token
    (from a prior ``AmazonAwsTaskInvisible``) and the per-session api_key
    extracted from captcha.js.  Optionally pair with ``aws_key`` /
    ``aws_iv`` / ``aws_context`` (decomposed gokuProps) for a real session
    fingerprint on the mp_verify step.
    """

    existing_token: str = ""      # always required

    _task_type: str = field(default="AmazonAwsTaskImage", init=False, repr=False)

    def to_api_payload(self) -> dict[str, Any]:
        if not self.aws_api_key:
            raise ValueError(
                "AmazonAwsTaskImage requires aws_api_key — the per-session api_key "
                "embedded in captcha.js (long encrypted string ending `_<num>_<num>`)."
            )
        if not self.existing_token:
            raise ValueError(
                "AmazonAwsTaskImage requires existing_token — mint one with "
                "AmazonAwsTaskInvisible first."
            )
        payload = self._payload()
        payload["existingToken"] = self.existing_token
        return payload


@dataclass(slots=True)
class AmazonAwsClassificationTask:
    """Standalone image classifier — no AWS WAF context, no proxy.

    Pass one or more base64-encoded PNG/JPG images; get back per-image
    (class, confidence, top_k) predictions over the 14-class label set
    (bag, bed, belts, binocular, bucket, clock, cooking_pot, fork, hat,
    scissors, seat, spoon, suitcase, umbrella).

    Provide ``image`` for a single classification or ``images`` for a
    batch — at least one of the two is required.  Adding ``target_class``
    flags each prediction with a ``matches_target`` boolean for callers
    that want a single target check.
    """

    image: str | None = None
    images: list[str] | None = None
    target_class: str | None = None
    top_k: int | None = None

    def to_api_payload(self) -> dict[str, Any]:
        if not self.image and not self.images:
            raise ValueError(
                "AmazonAwsClassificationTask requires image or images (base64 string(s))"
            )
        payload: dict[str, Any] = {"type": "AmazonAwsClassificationTask"}
        if self.image is not None:
            payload["image"] = self.image
        if self.images is not None:
            payload["images"] = self.images
        if self.target_class is not None:
            payload["targetClass"] = self.target_class
        if self.top_k is not None:
            payload["topK"] = self.top_k
        return payload


# Type alias for any task accepted by SolvexClient.solve().
AnyTask = (
    "FunCaptchaTask | AmazonAwsTask | AmazonAwsTaskInvisible "
    "| AmazonAwsTaskImage | AmazonAwsClassificationTask"
)


# ── Result types ───────────────────────────────────────────────────────────


@dataclass(slots=True)
class ClassificationTopKEntry:
    """One entry of ``ClassificationCell.top_k`` — second/third guesses."""

    class_name: str
    class_idx: int
    confidence: float


@dataclass(slots=True)
class ClassificationCell:
    """Per-image classification result returned by AmazonAwsClassificationTask.

    ``top_k`` lists the K highest-confidence classes (descending).
    ``matches_target`` is only set when the request supplied a target_class.
    """

    class_name: str
    class_idx: int
    confidence: float
    top_k: list[ClassificationTopKEntry]
    matches_target: bool | None = None


def _parse_classification_cell(raw: dict[str, Any]) -> ClassificationCell:
    """Convert a server-side prediction dict (snake_case fields the JSON uses)
    into the SDK's snake_case dataclass shape.  Server returns
    ``classIdx``/``topK``/``matchesTarget``; SDK exposes pythonic names.
    """
    top_k_raw = raw.get("topK") or raw.get("top_k") or []
    top_k = [
        ClassificationTopKEntry(
            class_name=t.get("class", ""),
            class_idx=int(t.get("classIdx", t.get("class_idx", 0))),
            confidence=float(t.get("confidence", 0.0)),
        )
        for t in top_k_raw
    ]
    matches = raw.get("matchesTarget", raw.get("matches_target"))
    return ClassificationCell(
        class_name=raw.get("class", ""),
        class_idx=int(raw.get("classIdx", raw.get("class_idx", 0))),
        confidence=float(raw.get("confidence", 0.0)),
        top_k=top_k,
        matches_target=matches,
    )


@dataclass(slots=True)
class TaskResult:
    """Result returned by getTaskResult.

    Token-issuing tasks (FunCaptcha, AmazonAws solving variants) populate
    ``token``.  ``AmazonAwsClassificationTask`` populates ``predictions``
    instead — ``token`` is empty in that case.  Always check which one is
    set before using.
    """

    task_id: str
    status: Literal["ready"]
    cost_usd: float
    token: str = ""
    predictions: list[ClassificationCell] | None = None
    # AmazonAws solving tasks set this to True when the visual + voucher step
    # actually ran (i.e. an api_key was supplied).  False on AmazonAwsTask
    # that degraded to invisible-only.  Absent / False on FunCaptcha and
    # classification — semantically meaningless for those task families.
    image_solved: bool = False
    create_time: int | None = None
    end_time: int | None = None
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def solve_seconds(self) -> float | None:
        if self.create_time is None or self.end_time is None:
            return None
        return max(0, self.end_time - self.create_time)

    @property
    def is_classification(self) -> bool:
        """True iff this result carries predictions (no token)."""
        return self.predictions is not None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
