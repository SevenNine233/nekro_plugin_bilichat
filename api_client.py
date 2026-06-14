"""bilichat-request API 客户端"""

import httpx
from nekro_agent.core import logger

from .models import Content, Dynamic, LiveRoom, SearchUp


class BilichatAPI:
    """bilichat-request API 客户端"""

    def __init__(self, base_url: str, token: str, timeout: int = 60):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client: httpx.AsyncClient | None = None
        self._timeout = timeout

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._headers,
                timeout=self._timeout,
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _get(self, url: str, **kwargs):
        client = await self._get_client()
        resp = await client.get(url, **kwargs)
        resp.raise_for_status()
        return resp

    async def _post(self, url: str, **kwargs):
        client = await self._get_client()
        resp = await client.post(url, **kwargs)
        resp.raise_for_status()
        return resp

    async def search_up(self, keyword: str, ps: int = 5) -> list[SearchUp] | None:
        """搜索 UP 主"""
        try:
            resp = await self._get("/tools/search_up", params={"keyword": keyword, "ps": ps})
            data = resp.json()
            if isinstance(data, list):
                return [SearchUp.model_validate(u) for u in data]
            return [SearchUp.model_validate(data)]
        except Exception as e:
            logger.error(f"[BilichatAPI] 搜索 UP 失败: {e}")
            return None

    async def sub_live(self, uid: int) -> LiveRoom | None:
        """获取单个 UP 直播状态"""
        try:
            resp = await self._get("/subs/live", params={"uid": uid})
            return LiveRoom.model_validate(resp.json())
        except Exception as e:
            logger.error(f"[BilichatAPI] 获取直播状态失败 uid={uid}: {e}")
            return None

    async def sub_lives(self, uids: list[int]) -> list[LiveRoom]:
        """批量获取多个 UP 直播状态"""
        try:
            resp = await self._post("/subs/lives", json=uids)
            raw = resp.json()
            data = raw if isinstance(raw, list) else [raw]
            return [LiveRoom.model_validate(lv) for lv in data]
        except Exception as e:
            logger.error(f"[BilichatAPI] 批量获取直播状态失败: {e}")
            return []

    async def subs_dynamic(self, uid: int, offset: int = 0) -> list[Dynamic]:
        """获取 UP 动态列表"""
        try:
            resp = await self._get("/subs/dynamic", params={"uid": uid, "offset": offset})
            return [Dynamic.model_validate(d) for d in resp.json()]
        except Exception as e:
            logger.error(f"[BilichatAPI] 获取动态失败 uid={uid}: {e}")
            return []

    async def content_dynamic(self, dynamic_id: int, quality: int = 75) -> Content | None:
        """获取动态内容截图"""
        try:
            resp = await self._get(
                "/content/dynamic",
                params={"dynamic_id": dynamic_id, "quality": quality},
            )
            return Content.model_validate(resp.json())
        except Exception as e:
            logger.error(f"[BilichatAPI] 获取动态截图失败 dyn_id={dynamic_id}: {e}")
            return None
