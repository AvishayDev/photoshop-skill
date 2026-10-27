"""Polite HTTP client for research providers: identifying User-Agent, per-host rate limiting,
retry with backoff on 429/5xx (honoring Retry-After), response size limits, and a small JSON cache."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from ..config import get_settings
from ..errors import ResearchError

MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_IMAGE_BYTES = 25 * 1024 * 1024


class PoliteClient:
    def __init__(self, min_interval: float = 1.0, cache_ttl: float = 24 * 3600, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = get_settings().user_agent
        self.min_interval = min_interval
        self.cache_ttl = cache_ttl
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def _wait(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._last.get(host, 0) + self.min_interval - now
            if delay > 0:
                time.sleep(delay)
            self._last[host] = time.monotonic()

    def _cache_path(self, url: str, params: dict | None) -> Path:
        key = hashlib.sha256((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()[:32]
        return get_settings().cache_dir / "http" / f"{key}.json"

    def get_json(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None,
                 use_cache: bool = True) -> Any:
        cp = self._cache_path(url, params)
        if use_cache and cp.exists() and time.time() - cp.stat().st_mtime < self.cache_ttl:
            try:
                return json.loads(cp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        resp = self._request(url, params=params, headers=headers)
        if len(resp.content) > MAX_JSON_BYTES:
            raise ResearchError("Provider response too large")
        try:
            data = resp.json()
        except ValueError as exc:
            raise ResearchError(f"Provider returned non-JSON from {urlparse(url).hostname}") from exc
        if use_cache:
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps(data), encoding="utf-8")
        return data

    def get_bytes(self, url: str, max_bytes: int = MAX_IMAGE_BYTES) -> tuple[bytes, str]:
        resp = self._request(url, stream=True)
        ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if not ctype.startswith("image/"):
            raise ResearchError(f"Expected an image, got content type '{ctype or 'unknown'}'")
        chunks, total = [], 0
        for chunk in resp.iter_content(65536):
            total += len(chunk)
            if total > max_bytes:
                raise ResearchError(f"Image exceeds {max_bytes // (1024 * 1024)} MB download limit")
            chunks.append(chunk)
        return b"".join(chunks), ctype

    def _request(self, url: str, params=None, headers=None, stream: bool = False, retries: int = 3,
                 max_total_wait: float = 25.0):
        parsed = urlparse(url)
        if parsed.scheme != "https":
            raise ResearchError("Only https URLs are fetched")
        last_exc: Exception | None = None
        waited = 0.0
        for attempt in range(retries):
            self._wait(parsed.hostname or "")
            try:
                resp = self.session.get(url, params=params, headers=headers, timeout=(10, 30), stream=stream)
            except requests.RequestException as exc:
                last_exc = exc
                pause = min(2 ** attempt, max(0.0, max_total_wait - waited))
                waited += pause
                time.sleep(pause)
                continue
            if resp.status_code in (429, 500, 502, 503, 504):
                ra = resp.headers.get("Retry-After")
                wait = float(ra) if ra and ra.isdigit() else 2 ** (attempt + 1)
                last_exc = ResearchError(f"{parsed.hostname} returned HTTP {resp.status_code}")
                pause = min(wait, max(0.0, max_total_wait - waited))
                if attempt < retries - 1 and pause > 0:
                    waited += pause
                    time.sleep(pause)
                continue
            if urlparse(resp.url).scheme != "https":
                raise ResearchError("Provider redirected to a non-https URL; refusing to follow")
            if resp.status_code >= 400:
                raise ResearchError(f"{parsed.hostname} returned HTTP {resp.status_code}",
                                    details={"body": resp.text[:300]})
            return resp
        raise ResearchError(f"Request to {parsed.hostname} failed after {retries} attempts: {last_exc}",
                            hint="The provider may be rate-limiting; wait and retry, or try another provider.")
