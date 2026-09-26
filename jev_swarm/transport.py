"""Small standard-library HTTP transport. Secrets are never included in errors."""
from __future__ import annotations
import asyncio
import json
import urllib.error
import urllib.request
from typing import Protocol
from .models import JSON

class Transport(Protocol):
    async def post(self, url: str, headers: dict[str, str], payload: JSON, timeout: float) -> JSON: ...

class ProviderError(RuntimeError):
    pass

class HTTPTransport:
    def __init__(self, retries: int = 2):
        self.retries = retries

    async def post(self, url: str, headers: dict[str, str], payload: JSON, timeout: float = 30) -> JSON:
        body = json.dumps(payload, allow_nan=False).encode()
        for attempt in range(self.retries + 1):
            try:
                return await asyncio.to_thread(self._post, url, headers, body, timeout)
            except urllib.error.HTTPError as exc:
                retry = exc.code in {429, 500, 502, 503, 504, 529}
                if retry and attempt < self.retries:
                    try:
                        delay = min(float(exc.headers.get("Retry-After", 2 ** attempt)), 10)
                    except (TypeError, ValueError):
                        delay = 2 ** attempt
                    await asyncio.sleep(max(0, delay))
                    continue
                if exc.code == 402:
                    message = "No API credits or billing access available. Add credits or redeem the provider's hackathon credits before retrying"
                elif exc.code in {401, 403}:
                    message = "Check key/account access"
                else:
                    message = "Check model, provider status and request limits"
                raise ProviderError(f"Provider HTTP {exc.code}. {message}.") from None
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < self.retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise ProviderError("Provider connection failed or timed out.") from None
        raise ProviderError("Provider retries exhausted")

    @staticmethod
    def _post(url: str, headers: dict[str, str], body: bytes, timeout: float) -> JSON:
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **headers}, method="POST")
        # Never forward provider credentials to a redirect destination.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, hdrs, newurl):
                return None
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise ProviderError("Provider response exceeded size limit")
            try:
                result = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                raise ProviderError("Provider returned invalid JSON") from None
            if not isinstance(result, dict):
                raise ProviderError("Provider returned an unexpected response")
            return result
