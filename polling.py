"""后台轮询任务 - 直播和动态检查"""

import asyncio
import base64
import time
import tempfile
import os

from nekro_agent.core import logger
from nekro_agent.api.message import send_text, send_image
from nekro_agent.schemas.agent_ctx import AgentCtx

from .api_client import BilichatAPI
from .subs_manager import SubsManager
from .push_formatter import format_live_start, format_live_end, format_dynamic
from .models import PushType, UP, DynamicType


class PollingService:
    """后台轮询服务"""

    def __init__(self, api: BilichatAPI, subs: SubsManager, config: dict):
        self._api = api
        self._subs = subs
        self._config = config
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        """启动后台轮询"""
        self._running = True
        live_interval = self._config.get("live_interval", 60)
        dynamic_interval = self._config.get("dynamic_interval", 300)
        logger.info(f"[Bilichat] 启动后台轮询: 直播间隔={live_interval}s, 动态间隔={dynamic_interval}s")
        self._tasks.append(asyncio.create_task(self._live_loop(live_interval)))
        self._tasks.append(asyncio.create_task(self._dynamic_loop(dynamic_interval)))

    async def stop(self):
        """停止后台轮询"""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _live_loop(self, interval: int):
        """直播检查循环"""
        await asyncio.sleep(10)  # 初次延迟
        while self._running:
            try:
                await self._check_live()
            except Exception:
                logger.exception("[Bilichat] 直播检查异常")
            await asyncio.sleep(interval)

    async def _dynamic_loop(self, interval: int):
        """动态检查循环"""
        await asyncio.sleep(20)  # 初次延迟
        while self._running:
            try:
                await self._check_dynamic()
            except Exception:
                logger.exception("[Bilichat] 动态检查异常")
            await asyncio.sleep(interval)

    async def _check_live(self):
        """检查所有已订阅 UP 的直播状态"""
        uids = self._subs.get_all_subscribed_uids()
        if not uids:
            return
        logger.trace(f"[Bilichat] 检查 {len(uids)} 个 UP 的直播状态")
        try:
            lives = await self._api.sub_lives(list(uids))
        except Exception as e:
            logger.error(f"[Bilichat] 批量获取直播状态失败: {e}")
            return

        lives_dict = {lv.uid: lv for lv in lives}
        for uid in uids:
            live = lives_dict.get(uid)
            status = self._subs.get_up_status(uid)

            if not live:
                continue

            # 更新 UP 名称
            if status.name != live.uname:
                status.name = live.uname

            # 首次获取，仅记录状态
            if status.live_status == -1:
                status.live_status = live.live_status
                status.live_time = live.live_time or 0
                self._subs.update_up_status(status)
                continue

            # 开播通知：之前不在直播，现在在直播
            if live.live_status == 1 and status.live_status != 1:
                status.live_status = 1
                status.live_time = live.live_time or int(time.time())
                self._subs.update_up_status(status)
                await self._push_live_start(uid, live.uname, live.title, live.room_id, live.cover_from_user)

            elif status.live_status == 1 and live.live_status != 1:
                if status.live_time > 1500000000:
                    elapsed = time.time() - status.live_time
                else:
                    logger.warning(f"[Bilichat] UP {uid} 下播但 live_time 无效 ({status.live_time})，跳过下播通知")
                    status.live_status = live.live_status
                    self._subs.update_up_status(status)
                    continue
                status.live_status = live.live_status
                self._subs.update_up_status(status)
                await self._push_live_end(uid, live.uname, elapsed)

            # 状态变更（非开播/下播）
            else:
                status.live_status = live.live_status
                if live.live_time:
                    status.live_time = live.live_time
                self._subs.update_up_status(status)

    async def _check_dynamic(self):
        """检查所有已订阅 UP 的新动态"""
        uids = self._subs.get_all_subscribed_uids()
        if not uids:
            return
        quality = self._config.get("browser_shot_quality", 75)

        for uid in uids:
            try:
                status = self._subs.get_up_status(uid)
                dyns = await self._api.subs_dynamic(uid)
                if not dyns:
                    continue

                # 首次获取，仅记录 offset
                if status.dyn_offset == -1:
                    status.dyn_offset = max(d.dyn_id for d in dyns)
                    self._subs.update_up_status(status)
                    continue

                # 筛选新动态
                new_dyns = sorted(
                    [d for d in dyns if d.dyn_id > status.dyn_offset],
                    key=lambda x: x.dyn_id,
                )
                for dyn in new_dyns:
                    content = await self._api.content_dynamic(dyn.dyn_id, quality)
                    b23 = content.b23 if content else ""
                    status.dyn_offset = dyn.dyn_id
                    self._subs.update_up_status(status)
                    await self._push_dynamic(uid, dyn.dyn_type, status.name, b23, content.img if content else "")
                    await asyncio.sleep(1)  # 避免推送过快

            except Exception as e:
                logger.exception(f"[Bilichat] 动态检查异常 uid={uid}: {e}")
                continue

    async def _push_live_start(self, uid: int, uname: str, title: str, room_id: int, cover_url: str):
        """推送开播通知"""
        use_rich_media = self._config.get("use_rich_media", True)
        chat_keys = self._subs.get_chat_keys_for_up(uid)

        # 封面图只下载一次，所有频道共用
        cover_data = None
        tmp_path = None
        if use_rich_media and cover_url:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(cover_url)
                    cover_data = resp.content
                tmp_path = os.path.join(tempfile.gettempdir(), f"bilichat_live_{uid}.jpg")
                with open(tmp_path, "wb") as f:
                    f.write(cover_data)
            except Exception:
                logger.warning(f"[Bilichat] 下载封面图失败 uid={uid}")
                cover_data = None
                tmp_path = None

        for chat_key in chat_keys:
            try:
                up = self._subs.get_up(chat_key, uid)
                if not up or up.live == PushType.IGNORE:
                    continue
                up_name = up.nickname or up.uname or uname
                at_all = up.live == PushType.AT_ALL

                ctx = await AgentCtx.create_by_chat_key(chat_key)

                if use_rich_media and tmp_path and cover_data:
                    try:
                        at_prefix = '[AT全体] ' if at_all else ''
                        text = f"{at_prefix}{up_name} 开播了: {title}\nhttps://live.bilibili.com/{room_id}"
                        await send_text(chat_key, text, ctx, record=False)
                        await send_image(chat_key, tmp_path, ctx, record=False)
                    except Exception:
                        text = format_live_start(up_name, title, room_id, at_all, rich_media=False)
                        await send_text(chat_key, text, ctx, record=False)
                else:
                    text = format_live_start(up_name, title, room_id, at_all, rich_media=False)
                    await send_text(chat_key, text, ctx, record=False)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"[Bilichat] 推送开播失败 chat_key={chat_key}: {e}")

        # 清理临时文件
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
    async def _push_live_end(self, uid: int, uname: str, elapsed: float):
        """推送下播通知"""
        chat_keys = self._subs.get_chat_keys_for_up(uid)
        for chat_key in chat_keys:
            try:
                up = self._subs.get_up(chat_key, uid)
                if not up or up.live == PushType.IGNORE:
                    continue
                up_name = up.nickname or up.uname or uname
                ctx = await AgentCtx.create_by_chat_key(chat_key)
                text = format_live_end(up_name, elapsed)
                await send_text(chat_key, text, ctx, record=False)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"[Bilichat] 推送下播失败 chat_key={chat_key}: {e}")

    async def _push_dynamic(self, uid: int, dyn_type: DynamicType, uname: str, b23: str, img_base64: str):
        """推送动态通知"""
        use_rich_media = self._config.get("use_rich_media", True)
        chat_keys = self._subs.get_chat_keys_for_up(uid)
        for chat_key in chat_keys:
            try:
                up = self._subs.get_up(chat_key, uid)
                if not up:
                    continue
                # 检查该类型动态的推送设置
                dyn_push_type = up.dynamic.get(dyn_type, PushType.PUSH)
                if dyn_push_type == PushType.IGNORE:
                    continue
                up_name = up.nickname or up.uname or uname
                at_all = dyn_push_type == PushType.AT_ALL

                ctx = await AgentCtx.create_by_chat_key(chat_key)

                if use_rich_media and img_base64:
                    try:
                        img_data = base64.b64decode(img_base64)
                        tmp_path = os.path.join(tempfile.gettempdir(), f"bilichat_dyn_{dyn_type}_{uid}.jpg")
                        with open(tmp_path, "wb") as f:
                            f.write(img_data)
                        text = f"{'[AT全体] ' if at_all else ''}{up_name} 发布了新动态\n{b23}"
                        await send_text(chat_key, text, ctx, record=False)
                        await send_image(chat_key, tmp_path, ctx, record=False)
                        os.remove(tmp_path)
                    except Exception:
                        text = format_dynamic(up_name, b23, at_all, rich_media=False)
                        await send_text(chat_key, text, ctx, record=False)
                else:
                    text = format_dynamic(up_name, b23, at_all, rich_media=False)
                    await send_text(chat_key, text, ctx, record=False)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"[Bilichat] 推送动态失败 chat_key={chat_key}: {e}")
