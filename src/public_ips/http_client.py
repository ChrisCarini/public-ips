from __future__ import annotations

import os
import random
import time

import httpx


class RetryingHttpClient:
    def __init__(
        self,
        *,
        timeout_connect: float = 5.0,
        timeout_read: float = 20.0,
        retries: int = 3,
    ) -> None:
        self._timeout = httpx.Timeout(
            connect=timeout_connect, read=timeout_read, write=timeout_read, pool=timeout_connect
        )
        self._retries = retries
        self._github_token = os.getenv("PUBLIC_IPS_GITHUB_TOKEN")

    def _headers_for(self, url: str) -> dict[str, str]:
        headers: dict[str, str] = {
            "User-Agent": "public-ips-updater",
        }
        if self._github_token and url.startswith("https://api.github.com/"):
            headers["Authorization"] = "Bearer " + self._github_token
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        return headers

    def get(self, url: str) -> tuple[int, bytes, str | None, str | None, str | None]:
        attempt = 0
        with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
            while True:
                response = client.get(url, headers=self._headers_for(url))
                if response.status_code not in {429, 500, 502, 503, 504}:
                    break
                attempt += 1
                if attempt > self._retries:
                    break
                sleep_s = min(8.0, (2**attempt) + random.uniform(0.0, 0.5))
                time.sleep(sleep_s)
            return (
                response.status_code,
                response.content,
                response.headers.get("content-type"),
                response.headers.get("etag"),
                response.headers.get("last-modified"),
            )
