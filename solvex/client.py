"""Sync + async Solvex API clients."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from .exceptions import SolvexError, TaskTimeoutError, exception_for
from .models import (
    AmazonAwsClassificationTask,
    AmazonAwsTask,
    AmazonAwsTaskImage,
    AmazonAwsTaskInvisible,
    FunCaptchaTask,
    TaskResult,
    _parse_classification_cell,
)

# Any task type accepted by .solve() / .create_task().  Kept loose because
# Python's Union types over Protocols are awkward — every task class
# exposes .to_api_payload() which is the only contract the client needs.
SolveTask = (
    FunCaptchaTask
    | AmazonAwsTask
    | AmazonAwsTaskInvisible
    | AmazonAwsTaskImage
    | AmazonAwsClassificationTask
)


def _build_task_result(task_id: str, data: dict[str, Any]) -> TaskResult:
    """Shape /getTaskResult's status='ready' payload into a TaskResult,
    handling both token-issuing solves and classification predictions.
    """
    sol = data.get("solution") or {}

    # Token path — FunCaptcha + AmazonAws (solving variants).
    token = sol.get("token")
    predictions = None

    # Classification path — convert the per-cell dicts into typed entries.
    raw_preds = sol.get("predictions")
    if isinstance(raw_preds, list):
        predictions = [_parse_classification_cell(p) for p in raw_preds]

    if not isinstance(token, str):
        token = ""

    if not token and predictions is None:
        raise SolvexError(
            "ready task carries neither solution.token nor solution.predictions"
        )

    return TaskResult(
        task_id=task_id,
        status="ready",
        token=token,
        predictions=predictions,
        # imageSolved is server-set on AmazonAws solving tasks; coerce to
        # bool because older server builds may omit the field entirely.
        image_solved=bool(sol.get("imageSolved", False)),
        cost_usd=float(data.get("cost") or 0.0),
        create_time=data.get("createTime"),
        end_time=data.get("endTime"),
        raw=data,
    )

DEFAULT_BASE_URL = "https://api.solvex.run"
DEFAULT_POLL_INTERVAL = 0.5        # seconds between getTaskResult calls
DEFAULT_TIMEOUT = 120.0            # end-to-end budget for solve()
DEFAULT_HTTP_TIMEOUT = 30.0        # per-request httpx timeout


# ──────────────────────────── helpers ────────────────────────────

def _handle_envelope(body: dict[str, Any]) -> dict[str, Any]:
    """Raise if the response carries a non-zero antiCaptcha errorId."""
    eid = body.get("errorId")
    if not isinstance(eid, int) or eid == 0:
        return body
    raise exception_for(
        eid,
        body.get("errorCode"),
        body.get("errorDescription"),
    )


def _build_body(client_key: str, extra: dict[str, Any]) -> dict[str, Any]:
    return {"clientKey": client_key, **extra}


# ──────────────────────────── sync ────────────────────────────

class SolvexClient:
    """
    Synchronous Solvex client.

        from solvex import SolvexClient, FunCaptchaTask, Proxy

        with SolvexClient("sk_live_…") as sx:
            result = sx.solve(FunCaptchaTask(
                website_url="https://roblox.com",
                website_public_key="476068BF-…",
                proxy=Proxy.from_url("http://user:pass@1.2.3.4:8080"),
            ))
            print(result.token)
    """

    def __init__(
        self,
        client_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        http_timeout: float = DEFAULT_HTTP_TIMEOUT,
        session: httpx.Client | None = None,
    ):
        if not client_key:
            raise ValueError("client_key is required")
        self.client_key = client_key
        self.base_url = base_url.rstrip("/")
        self._owns_session = session is None
        self._session = session or httpx.Client(timeout=http_timeout, follow_redirects=False)

    def __enter__(self) -> "SolvexClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_session:
            self._session.close()

    # ─── low-level ───

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            r = self._session.post(url, json=body)
        except httpx.HTTPError as e:
            raise SolvexError(f"network error calling {path}: {e}") from e
        try:
            data = r.json()
        except ValueError as e:
            raise SolvexError(f"{path}: non-JSON response (HTTP {r.status_code})") from e
        return _handle_envelope(data)

    def create_task(self, task: SolveTask, *, idempotency_key: str | None = None) -> str:
        body: dict[str, Any] = {"task": task.to_api_payload()}
        if idempotency_key is not None:
            body["idempotencyKey"] = idempotency_key
        data = self._post("/createTask", _build_body(self.client_key, body))
        task_id = data.get("taskId")
        if not isinstance(task_id, str):
            raise SolvexError("createTask response missing taskId")
        return task_id

    def get_task_result(self, task_id: str) -> dict[str, Any]:
        return self._post(
            "/getTaskResult",
            _build_body(self.client_key, {"taskId": task_id}),
        )

    def get_balance(self) -> float:
        data = self._post("/getBalance", _build_body(self.client_key, {}))
        bal = data.get("balance")
        if not isinstance(bal, (int, float)):
            raise SolvexError("getBalance response missing balance")
        return float(bal)

    # ─── high-level ───

    def solve(
        self,
        task: SolveTask,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        idempotency_key: str | None = None,
    ) -> TaskResult:
        """Submit a task, poll until ready, return the result.

        Works for every task type the SDK supports — token-issuing
        (FunCaptcha + AmazonAws solving) and classification.  Inspect
        ``result.is_classification`` (or ``result.predictions``) to tell
        them apart.

        Raises ``TaskTimeoutError`` if the task doesn't complete inside
        ``timeout`` seconds. Raises ``TaskFailedError`` if the server reports
        failure (credits are refunded automatically in that case).
        """
        task_id = self.create_task(task, idempotency_key=idempotency_key)
        deadline = time.monotonic() + timeout

        while True:
            data = self.get_task_result(task_id)
            status = data.get("status")
            if status == "ready":
                return _build_task_result(task_id, data)
            # status == "processing" or still "pending": keep polling
            if time.monotonic() >= deadline:
                raise TaskTimeoutError(
                    f"task {task_id} did not finish within {timeout:.1f}s",
                )
            remaining = deadline - time.monotonic()
            time.sleep(min(poll_interval, max(0.05, remaining)))


# ──────────────────────────── async ────────────────────────────

class AsyncSolvexClient:
    """Async counterpart. Same API, httpx.AsyncClient under the hood."""

    def __init__(
        self,
        client_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        http_timeout: float = DEFAULT_HTTP_TIMEOUT,
        session: httpx.AsyncClient | None = None,
    ):
        if not client_key:
            raise ValueError("client_key is required")
        self.client_key = client_key
        self.base_url = base_url.rstrip("/")
        self._owns_session = session is None
        self._session = session or httpx.AsyncClient(
            timeout=http_timeout, follow_redirects=False,
        )

    async def __aenter__(self) -> "AsyncSolvexClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_session:
            await self._session.aclose()

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            r = await self._session.post(url, json=body)
        except httpx.HTTPError as e:
            raise SolvexError(f"network error calling {path}: {e}") from e
        try:
            data = r.json()
        except ValueError as e:
            raise SolvexError(f"{path}: non-JSON response (HTTP {r.status_code})") from e
        return _handle_envelope(data)

    async def create_task(
        self, task: SolveTask, *, idempotency_key: str | None = None,
    ) -> str:
        body: dict[str, Any] = {"task": task.to_api_payload()}
        if idempotency_key is not None:
            body["idempotencyKey"] = idempotency_key
        data = await self._post("/createTask", _build_body(self.client_key, body))
        task_id = data.get("taskId")
        if not isinstance(task_id, str):
            raise SolvexError("createTask response missing taskId")
        return task_id

    async def get_task_result(self, task_id: str) -> dict[str, Any]:
        return await self._post(
            "/getTaskResult",
            _build_body(self.client_key, {"taskId": task_id}),
        )

    async def get_balance(self) -> float:
        data = await self._post("/getBalance", _build_body(self.client_key, {}))
        bal = data.get("balance")
        if not isinstance(bal, (int, float)):
            raise SolvexError("getBalance response missing balance")
        return float(bal)

    async def solve(
        self,
        task: SolveTask,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        idempotency_key: str | None = None,
    ) -> TaskResult:
        task_id = await self.create_task(task, idempotency_key=idempotency_key)
        deadline = time.monotonic() + timeout

        while True:
            data = await self.get_task_result(task_id)
            status = data.get("status")
            if status == "ready":
                return _build_task_result(task_id, data)
            if time.monotonic() >= deadline:
                raise TaskTimeoutError(
                    f"task {task_id} did not finish within {timeout:.1f}s",
                )
            remaining = deadline - time.monotonic()
            await asyncio.sleep(min(poll_interval, max(0.05, remaining)))
