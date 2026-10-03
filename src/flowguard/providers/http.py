from typing import Any

import httpx

from flowguard.providers.base import SapProviderError


class ODataHttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float = 15,
    ) -> None:
        self.client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, auth=auth, timeout=timeout
        )

    async def get_collection(self, path: str, params: dict[str, Any] | None = None) -> list[dict]:
        results: list[dict] = []
        next_path: str | None = path
        next_params = params
        while next_path:
            response = await self.client.get(next_path, params=next_params)
            if response.is_error:
                raise SapProviderError(
                    f"SAP GET {response.request.url} failed with HTTP {response.status_code}"
                )
            payload = response.json()
            if "d" in payload:
                data = payload["d"]
                page = data.get("results", [data]) if isinstance(data, dict) else data
                next_path = data.get("__next") if isinstance(data, dict) else None
            else:
                page = payload.get("value", [])
                next_path = payload.get("@odata.nextLink")
            results.extend(page)
            next_params = None
        return results

    async def health(self, path: str = "/health") -> bool:
        try:
            response = await self.client.get(path)
            return response.is_success
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        await self.client.aclose()
