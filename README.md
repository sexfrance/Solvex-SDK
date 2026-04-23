# solvex-sdk

Python client for the [Solvex](https://solvex.run) FunCaptcha solving API.

## Install

```bash
pip install solvex-sdk
# or, from this repo:
pip install .
```

The distribution is published as `solvex-sdk`; the import name is `solvex`.

Requires Python 3.10+. Depends on `httpx`.

## Quickstart

```python
from solvex import SolvexClient, FunCaptchaTask, Proxy

with SolvexClient("sk_live_...") as sx:
    result = sx.solve(FunCaptchaTask(
        website_url="https://roblox.com",
        website_public_key="476068BF-9607-4799-B53D-966BE98E2B81",
        proxy=Proxy.from_url("http://user:pass@184.82.39.210:8080"),
    ))
    print(result.token)
    print(f"cost=${result.cost_usd}  solved in {result.solve_seconds}s")
```

A proxy is **required** — Solvex does not run proxyless solves.

## Supported site keys

Solvex rejects `websitePublicKey` values it doesn't know, rather than silently
forwarding bad context (wrong `surl`, wrong `location.href`, wrong `referrer`)
that Arkose would quietly suppress a token for. The currently-registered keys:

| Label          | `websitePublicKey`                     |
|----------------|----------------------------------------|
| Roblox Login   | `476068BF-9607-4799-B53D-966BE98E2B81` |
| Roblox Signup  | `A2A14B1D-1AF3-C791-9BBC-EE33CC7A0A6F` |

Passing anything else raises `UnsupportedSiteKeyError` (`errorId: 23`) — contact
support to add the site you need.

## Logged-in sessions (blob + cookies)

When the challenge is tied to a logged-in Roblox session (e.g. authenticated
actions that hand you a `dataExchangeBlob`), pass the blob in `data` **and** the
matching session cookie string in `cookies`. Without the cookie Arkose will
treat the session as mismatched and suppress the token:

```python
result = sx.solve(FunCaptchaTask(
    website_url="https://www.roblox.com",
    website_public_key="476068BF-9607-4799-B53D-966BE98E2B81",
    proxy=Proxy.from_url("http://user:pass@1.2.3.4:8080"),
    data=roblox_data_exchange_blob,
    cookies=".ROBLOSECURITY=...; RBXEventTrackerV2=...;",
))
```

### Cookie formats

The API accepts cookies in any of the shapes you'd get from common clients —
they're normalized to a `Cookie:` header server-side:

```python
# Raw header string (default)
cookies=".ROBLOSECURITY=...; RBXEventTrackerV2=..."

# Python requests
cookies=session.cookies.get_dict()

# rnet — same dict shape
cookies=dict(client.cookies)

# Playwright / Selenium / Puppeteer
cookies=[{"name": ".ROBLOSECURITY", "value": "..."}, {"name": "RBXEventTrackerV2", "value": "..."}]

# List of pair strings
cookies=[".ROBLOSECURITY=...", "RBXEventTrackerV2=..."]
```

## PoW-flagged sessions

When Arkose returns `pow=true`, the server can solve the PoW challenge and
still hand you a token instead of failing. Opt in with `solve_pow=True` —
it trades 1–3s (C++ fast path) or 15–30s (Node fallback) of latency for a
higher success rate on flagged sessions. Billed as a normal solve.

```python
task = FunCaptchaTask(..., solve_pow=True)
```

## Async

```python
import asyncio
from solvex import AsyncSolvexClient, FunCaptchaTask, Proxy

async def main():
    async with AsyncSolvexClient("sk_live_...") as sx:
        result = await sx.solve(FunCaptchaTask(
            website_url="https://roblox.com",
            website_public_key="476068BF-9607-4799-B53D-966BE98E2B81",
            proxy=Proxy.from_url("socks5://184.82.39.210:1080"),
            use_http3=True,   # None = server default (enabled)
        ))
        print(result.token)

asyncio.run(main())
```

## Low-level

If you want to manage polling yourself:

```python
task_id = sx.create_task(task)
while True:
    r = sx.get_task_result(task_id)
    if r["status"] == "ready":
        print(r["solution"]["token"])
        break
```

## Balance

```python
print(f"${sx.get_balance():.4f} remaining")
```

## Errors

Every non-zero `errorId` raises a typed exception:

| Exception                   | errorId | Meaning                             |
|-----------------------------|---------|-------------------------------------|
| `InvalidKeyError`           | 1       | clientKey missing / bad / revoked   |
| `UnsupportedTaskError`      | 2, 22   | task type not enabled               |
| `UnsupportedSiteKeyError`   | 23      | `websitePublicKey` not registered — contact support |
| `InsufficientCreditsError`  | 10      | account balance too low             |
| `TaskFailedError`           | 12      | solver couldn't produce a token (credits refunded) |
| `TaskNotFoundError`         | 16      | unknown taskId                      |
| `RateLimitedError`          | 31      | per-key or per-user rate limit      |
| `TaskTimeoutError`          | 40      | task exceeded server timeout / client wait |

Catch `SolvexError` to catch everything.

```python
from solvex import SolvexClient, TaskFailedError, RateLimitedError

try:
    result = sx.solve(task, timeout=90)
except TaskFailedError:
    # server already refunded — retry with fresh proxy
    ...
except RateLimitedError:
    time.sleep(5)
```

## Idempotency

Pass `idempotency_key=` to guard against double-billing on retries. Replays
within 24h return the same `taskId` without a second charge.

```python
sx.solve(task, idempotency_key=f"user-42-{run_id}")
```

## HTTP/3

Set `use_http3=False` on the task to force HTTP/2 (useful when debugging
proxies that mangle h3). Default is server-side (h3 enabled).

## Browser profile

Set `browser=` to route the solve through a specific fingerprints_v2 profile.
Accepts a family alias (`"firefox"`, `"chrome"`, `"brave"`, `"edge"`,
`"safari"`) or a specific profile name (`"firefox_win_140"`,
`"chrome_win_141"`, etc.). Omit or pass `"auto"` for the legacy Safari path.

```python
task = FunCaptchaTask(..., browser="firefox")
```

## License

MIT.
