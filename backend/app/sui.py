from urllib.parse import urljoin
import httpx

def normalize_base_url(base_url: str) -> str:
    u = base_url.rstrip("/") + "/"
    # Accept either https://host/app or https://host/app/apiv2
    if u.endswith("/apiv2/"):
        return u
    return urljoin(u, "apiv2/")

class SUIClient:
    def __init__(self, base_url: str, token: str, verify_tls: bool = True, timeout: int = 8):
        self.api = normalize_base_url(base_url)
        self.headers = {"Token": token}
        self.verify_tls = verify_tls
        self.timeout = timeout

    async def _request(self, method: str, endpoint: str, **kwargs):
        async with httpx.AsyncClient(verify=self.verify_tls, timeout=self.timeout, follow_redirects=True) as c:
            r = await c.request(method, self.api + endpoint.lstrip("/"), headers=self.headers, **kwargs)
            r.raise_for_status()
            try:
                body = r.json()
            except Exception:
                return {"success": True, "raw": r.text}
            if isinstance(body, dict) and body.get("success") is False:
                raise RuntimeError(body.get("msg") or "S-UI returned success=false")
            return body

    async def status(self):
        return await self._request("GET", "status", params={"r":"cpu,mem,net,sys,sbd,dsk,swp,dio"})

    async def inbounds(self):
        return await self._request("GET", "inbounds")

    async def clients(self):
        return await self._request("GET", "clients")

    async def onlines(self):
        return await self._request("GET", "onlines")

    async def settings(self):
        return await self._request("GET", "settings")

    async def raw_get(self, endpoint: str, params: dict|None=None):
        allowed = {"load","inbounds","outbounds","endpoints","services","tls","clients","config","users",
                   "settings","stats","status","onlines","logs","changes","keypairs","getdb"}
        if endpoint not in allowed:
            raise ValueError("endpoint not allowed")
        return await self._request("GET", endpoint, params=params or {})

    async def save(self, obj: str, action: str, data, init_users: str|None=None):
        payload = {"object": obj, "action": action, "data": data}
        if init_users is not None:
            payload["initUsers"] = init_users
        return await self._request("POST", "save", json=payload)

    async def restart_core(self):
        return await self._request("POST", "restartSb")

    async def restart_app(self):
        return await self._request("POST", "restartApp")
