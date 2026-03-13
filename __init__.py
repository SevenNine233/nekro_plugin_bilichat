"""
NekroAgent BiliChat 插件

复刻 nonebot-plugin-bilichat 的核心功能：
- B站内容解析（视频、专栏、动态）
- UP主订阅管理
- 动态/直播推送（通过异步任务实现）

依赖 bilichat-request 服务
"""

import asyncio
import time
from typing import Any, Dict, List, Literal, Optional

import httpx
from nekro_agent.api import core
from nekro_agent.api.plugin import ConfigBase, ExtraField, NekroPlugin, SandboxMethodType
from nekro_agent.api.schemas import AgentCtx
from nekro_agent.services.plugin.task import AsyncTaskHandle, TaskCtl, task
from pydantic import BaseModel, Field

# 插件元信息
plugin = NekroPlugin(
    name="BiliChat",
    module_name="bilichat",
    description="B站内容解析与UP主订阅推送插件，支持视频/专栏/动态解析、订阅管理、动态直播推送",
    version="1.0.0",
    author="SevenNine233",
    url="https://github.com/SevenNine233/nekro_plugin_bilichat",
)


# =====================
# 数据模型
# =====================

class PushType:
    """推送类型枚举"""
    PUSH = "PUSH"        # 正常推送
    AT_ALL = "AT_ALL"    # @全体成员
    IGNORE = "IGNORE"    # 忽略


# 忽略的动态类型（广告、直播推荐等）
IGNORED_DYNAMIC_TYPES = {
    "DYNAMIC_TYPE_AD",           # 广告
    "DYNAMIC_TYPE_LIVE",         # 直播预告
    "DYNAMIC_TYPE_LIVE_RCMD",    # 直播推荐
    "DYNAMIC_TYPE_BANNER",       # 横幅
}


class UPInfo(BaseModel):
    """UP主信息"""
    uid: int
    """UP主UID"""
    uname: str = ""
    """UP主用户名"""
    nickname: str = ""
    """自定义昵称"""
    note: str = ""
    """备注"""
    live_push: str = PushType.PUSH
    """直播推送方式"""
    dynamic_push: str = PushType.PUSH
    """动态推送方式"""


class SubscriptionData(BaseModel):
    """订阅数据"""
    ups: Dict[int, UPInfo] = {}
    """订阅的UP主列表 {uid: UPInfo}"""


class PushState(BaseModel):
    """推送状态"""
    dynamic_offsets: Dict[int, int] = {}
    """动态偏移量 {uid: last_dyn_id}"""
    live_status: Dict[int, int] = {}
    """直播状态 {uid: status} 0=未开播, 1=直播中"""
    live_time: Dict[int, int] = {}
    """直播开始时间 {uid: timestamp}"""


# =====================
# 配置系统
# =====================

@plugin.mount_config()
class BiliChatConfig(ConfigBase):
    """BiliChat 插件配置"""

    # API 配置
    api_url: str = Field(
        default="http://192.168.0.102:40432",
        title="BiliChat API 地址",
        description="bilichat-request 服务的 API 地址",
        json_schema_extra=ExtraField(required=True).model_dump()
    )
    api_token: str = Field(
        default="xY8rL2pQ9sN4wT7zK",
        title="API Token",
        description="bilichat-request 服务的访问令牌",
        json_schema_extra=ExtraField(is_secret=True).model_dump()
    )

    # 解析配置
    parse_video: bool = Field(
        default=True,
        title="解析视频",
        description="是否解析B站视频链接"
    )
    parse_dynamic: bool = Field(
        default=True,
        title="解析动态",
        description="是否解析B站动态链接"
    )
    parse_column: bool = Field(
        default=True,
        title="解析专栏",
        description="是否解析B站专栏链接"
    )
    screenshot_quality: int = Field(
        default=75,
        title="截图质量",
        description="浏览器截图质量 (10-100)",
        ge=10,
        le=100
    )

    # 订阅推送配置
    enable_push: bool = Field(
        default=True,
        title="启用推送",
        description="是否启用动态和直播推送功能"
    )
    dynamic_interval: int = Field(
        default=300,
        title="动态轮询间隔",
        description="动态检查间隔（秒），最小 60 秒",
        ge=60
    )
    live_interval: int = Field(
        default=60,
        title="直播轮询间隔",
        description="直播状态检查间隔（秒），最小 30 秒",
        ge=30
    )
    use_rich_media: bool = Field(
        default=True,
        title="使用富媒体消息",
        description="推送时是否发送图片，关闭则只发送纯文本"
    )


# 获取配置实例
config: BiliChatConfig = plugin.get_config(BiliChatConfig)


# =====================
# API 客户端
# =====================

class BiliChatAPI:
    """BiliChat API 客户端"""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=60.0
            )
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs) -> Dict[str, Any]:
        """发送HTTP请求"""
        client = await self._get_client()
        try:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"API 请求失败: {e.response.status_code} - {e.response.text}")
        except httpx.RequestError as e:
            raise Exception(f"网络请求错误: {e}")

    async def _get(self, url: str, **kwargs) -> Dict[str, Any]:
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs) -> Dict[str, Any]:
        return await self._request("POST", url, **kwargs)

    # 内容解析 API
    async def parse_content(self, bililink: str) -> Dict[str, Any]:
        """解析B站内容（自动识别类型）"""
        return await self._get("/content/", params={"bililink": bililink})

    async def parse_video(self, video_id: str, quality: int = 75) -> Dict[str, Any]:
        """解析视频"""
        return await self._get("/content/video", params={"video_id": video_id, "quality": quality})

    async def parse_dynamic(self, dynamic_id: str, quality: int = 75) -> Dict[str, Any]:
        """解析动态"""
        return await self._get("/content/dynamic", params={"dynamic_id": dynamic_id, "quality": quality})

    async def parse_column(self, cvid: str, quality: int = 75) -> Dict[str, Any]:
        """解析专栏"""
        return await self._get("/content/column", params={"cvid": cvid, "quality": quality})

    # 订阅 API
    async def get_live_status(self, uid: int) -> Dict[str, Any]:
        """获取单个UP主直播状态"""
        return await self._get("/subs/live", params={"uid": uid})

    async def get_live_status_batch(self, uids: List[int]) -> List[Dict[str, Any]]:
        """批量获取UP主直播状态"""
        return await self._post("/subs/lives", json=uids)

    async def get_dynamics(self, uid: int, offset: int = 0) -> List[Dict[str, Any]]:
        """获取UP主动态列表"""
        return await self._get("/subs/dynamic", params={"uid": uid, "offset": offset})

    # 工具 API
    async def search_up(self, keyword: str, page_size: int = 5) -> List[Dict[str, Any]]:
        """搜索UP主"""
        result = await self._get("/tools/search_up", params={"keyword": keyword, "ps": page_size})
        if isinstance(result, list):
            return result
        return [result]

    async def b23_extract(self, b23_url: str) -> str:
        """解析 b23 短链接"""
        client = await self._get_client()
        response = await client.get("/tools/b23_extract", params={"url": b23_url})
        return response.text

    async def b23_generate(self, url: str) -> str:
        """生成 b23 短链接"""
        client = await self._get_client()
        response = await client.get("/tools/b23_generate", params={"url": url})
        return response.text

    async def check_health(self) -> bool:
        """检查API健康状态"""
        try:
            await self._get("/version")
            return True
        except Exception:
            return False


def get_api() -> BiliChatAPI:
    """获取API客户端实例"""
    return BiliChatAPI(config.api_url, config.api_token)


# =====================
# 订阅管理器
# =====================

class SubscriptionManager:
    """订阅管理器"""

    SUBSCRIPTION_KEY = "subscriptions"
    PUSH_STATE_KEY = "push_state"

    @staticmethod
    async def get_subscriptions(chat_key: str) -> SubscriptionData:
        """获取会话的订阅数据"""
        data_str = await plugin.store.get(chat_key=chat_key, store_key=SubscriptionManager.SUBSCRIPTION_KEY)
        if data_str:
            return SubscriptionData.model_validate_json(data_str)
        return SubscriptionData()

    @staticmethod
    async def save_subscriptions(chat_key: str, data: SubscriptionData):
        """保存会话的订阅数据"""
        await plugin.store.set(
            chat_key=chat_key,
            store_key=SubscriptionManager.SUBSCRIPTION_KEY,
            value=data.model_dump_json()
        )

    @staticmethod
    async def get_push_state(chat_key: str) -> PushState:
        """获取推送状态"""
        data_str = await plugin.store.get(chat_key=chat_key, store_key=SubscriptionManager.PUSH_STATE_KEY)
        if data_str:
            return PushState.model_validate_json(data_str)
        return PushState()

    @staticmethod
    async def save_push_state(chat_key: str, state: PushState):
        """保存推送状态"""
        await plugin.store.set(
            chat_key=chat_key,
            store_key=SubscriptionManager.PUSH_STATE_KEY,
            value=state.model_dump_json()
        )

    @staticmethod
    async def add_subscription(chat_key: str, uid: int, uname: str, nickname: str = "") -> str:
        """添加订阅"""
        data = await SubscriptionManager.get_subscriptions(chat_key)
        
        if uid in data.ups:
            up = data.ups[uid]
            if nickname:
                up.nickname = nickname
            up.uname = uname
        else:
            data.ups[uid] = UPInfo(uid=uid, uname=uname, nickname=nickname)
        
        await SubscriptionManager.save_subscriptions(chat_key, data)
        return f"已订阅 UP主 {nickname or uname} (UID: {uid})"

    @staticmethod
    async def remove_subscription(chat_key: str, uid: int) -> str:
        """移除订阅"""
        data = await SubscriptionManager.get_subscriptions(chat_key)
        
        if uid not in data.ups:
            return f"未订阅 UID {uid} 的UP主"
        
        up = data.ups.pop(uid)
        await SubscriptionManager.save_subscriptions(chat_key, data)
        return f"已取消订阅 {up.nickname or up.uname} (UID: {uid})"

    @staticmethod
    async def list_subscriptions(chat_key: str) -> str:
        """列出订阅"""
        data = await SubscriptionManager.get_subscriptions(chat_key)
        
        if not data.ups:
            return "当前会话未订阅任何UP主"
        
        lines = [f"共订阅 {len(data.ups)} 位UP主:"]
        for i, (uid, up) in enumerate(data.ups.items(), 1):
            name = up.nickname or up.uname
            lines.append(f"{i}. {name} (UID: {uid})")
        
        return "\n".join(lines)

    @staticmethod
    async def set_push_type(chat_key: str, uid: int, push_type: str, content_type: str = "all") -> str:
        """设置推送类型"""
        data = await SubscriptionManager.get_subscriptions(chat_key)
        
        if uid not in data.ups:
            return f"未订阅 UID {uid} 的UP主"
        
        up = data.ups[uid]
        
        if content_type in ("all", "live"):
            up.live_push = push_type
        if content_type in ("all", "dynamic"):
            up.dynamic_push = push_type
        
        await SubscriptionManager.save_subscriptions(chat_key, data)
        return f"已设置 {up.nickname or up.uname} 的推送方式为 {push_type}"


# =====================
# 推送任务
# =====================

@plugin.mount_async_task("push_task")
async def push_task(
    handle: AsyncTaskHandle,
    chat_key: str,
) -> None:
    """
    推送异步任务
    
    负责定时检查订阅的UP主动态和直播状态，并推送通知
    """
    import asyncio
    from nekro_agent.services.message_service import message_service
    
    plugin.logger.info(f"[BiliChat] 推送任务启动: {chat_key}")
    
    api = get_api()
    last_dynamic_check = 0
    last_live_check = 0
    
    while not handle.is_cancelled:
        try:
            # 获取订阅数据
            sub_data = await SubscriptionManager.get_subscriptions(chat_key)
            push_state = await SubscriptionManager.get_push_state(chat_key)
            
            if not sub_data.ups:
                # 没有订阅，等待后重试
                await asyncio.sleep(60)
                continue
            
            current_time = time.time()
            
            # === 动态检查 ===
            if current_time - last_dynamic_check >= config.dynamic_interval:
                last_dynamic_check = current_time
                plugin.logger.debug(f"[BiliChat] 检查动态: {chat_key}")
                
                for uid, up in sub_data.ups.items():
                    if up.dynamic_push == PushType.IGNORE:
                        continue
                    
                    if handle.is_cancelled:
                        break
                    
                    try:
                        dynamics = await api.get_dynamics(uid)
                        
                        if not dynamics:
                            continue
                        
                        # 初始化偏移量
                        if uid not in push_state.dynamic_offsets:
                            push_state.dynamic_offsets[uid] = max(d["dyn_id"] for d in dynamics) if dynamics else 0
                            await SubscriptionManager.save_push_state(chat_key, push_state)
                            continue
                        
                        last_offset = push_state.dynamic_offsets[uid]
                        new_dynamics = [d for d in dynamics if d["dyn_id"] > last_offset]
                        
                        for dyn in sorted(new_dynamics, key=lambda x: x["dyn_id"]):
                            dyn_type = dyn.get("dyn_type", "")
                            
                            # 跳过忽略的类型
                            if dyn_type in IGNORED_DYNAMIC_TYPES:
                                continue
                            
                            dyn_id = dyn["dyn_id"]
                            up_name = up.nickname or up.uname or f"UID:{uid}"
                            
                            # 推送动态
                            push_text = f"📺 {up_name} 发布了新动态\n"
                            
                            if config.use_rich_media:
                                try:
                                    content = await api.parse_dynamic(str(dyn_id), config.screenshot_quality)
                                    b23 = content.get("b23", "")
                                    push_text += f"链接: {b23}"
                                except Exception as e:
                                    plugin.logger.warning(f"[BiliChat] 解析动态失败: {e}")
                                    push_text += f"https://t.bilibili.com/{dyn_id}"
                            else:
                                push_text += f"https://t.bilibili.com/{dyn_id}"
                            
                            # 发送推送
                            try:
                                await message_service.push_system_message(
                                    chat_key=chat_key,
                                    agent_messages=push_text,
                                    trigger_agent=False,
                                )
                                plugin.logger.info(f"[BiliChat] 推送动态: {up_name} - {dyn_id}")
                            except Exception as e:
                                plugin.logger.error(f"[BiliChat] 推送失败: {e}")
                            
                            # 更新偏移量
                            push_state.dynamic_offsets[uid] = dyn_id
                            await SubscriptionManager.save_push_state(chat_key, push_state)
                            
                            await asyncio.sleep(1)  # 避免频繁请求
                        
                    except Exception as e:
                        plugin.logger.error(f"[BiliChat] 检查动态失败 (UID:{uid}): {e}")
            
            # === 直播检查 ===
            if current_time - last_live_check >= config.live_interval:
                last_live_check = current_time
                plugin.logger.debug(f"[BiliChat] 检查直播: {chat_key}")
                
                live_uids = [uid for uid, up in sub_data.ups.items() if up.live_push != PushType.IGNORE]
                
                if live_uids:
                    try:
                        live_statuses = await api.get_live_status_batch(live_uids)
                        live_map = {live["uid"]: live for live in live_statuses}
                        
                        for uid, up in sub_data.ups.items():
                            if up.live_push == PushType.IGNORE:
                                continue
                            
                            live_info = live_map.get(uid)
                            if not live_info:
                                continue
                            
                            live_status = live_info.get("live_status", 0)
                            prev_status = push_state.live_status.get(uid, -1)
                            
                            up_name = up.nickname or up.uname or live_info.get("uname", f"UID:{uid}")
                            
                            # 开播通知: 之前未开播，现在直播中
                            if live_status == 1 and prev_status != 1:
                                title = live_info.get("title", "无标题")
                                room_id = live_info.get("room_id", "")
                                
                                push_text = f"🔴 {up_name} 开播了!\n"
                                push_text += f"标题: {title}\n"
                                push_text += f"直播间: https://live.bilibili.com/{room_id}"
                                
                                try:
                                    await message_service.push_system_message(
                                        chat_key=chat_key,
                                        agent_messages=push_text,
                                        trigger_agent=False,
                                    )
                                    plugin.logger.info(f"[BiliChat] 推送开播: {up_name}")
                                except Exception as e:
                                    plugin.logger.error(f"[BiliChat] 推送开播失败: {e}")
                            
                            # 下播通知: 之前直播中，现在未开播
                            elif live_status != 1 and prev_status == 1:
                                push_text = f"⏹️ {up_name} 下播了"
                                
                                try:
                                    await message_service.push_system_message(
                                        chat_key=chat_key,
                                        agent_messages=push_text,
                                        trigger_agent=False,
                                    )
                                    plugin.logger.info(f"[BiliChat] 推送下播: {up_name}")
                                except Exception as e:
                                    plugin.logger.error(f"[BiliChat] 推送下播失败: {e}")
                            
                            # 更新状态
                            push_state.live_status[uid] = live_status
                            await SubscriptionManager.save_push_state(chat_key, push_state)
                        
                    except Exception as e:
                        plugin.logger.error(f"[BiliChat] 检查直播失败: {e}")
            
            # 等待下一次检查
            await asyncio.sleep(min(config.live_interval, config.dynamic_interval) // 2)
            
        except Exception as e:
            plugin.logger.error(f"[BiliChat] 推送任务异常: {e}")
            await asyncio.sleep(30)
    
    plugin.logger.info(f"[BiliChat] 推送任务停止: {chat_key}")


# =====================
# 沙盒方法 - 内容解析
# =====================

@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    name="bilibili_parse",
    description="解析B站链接内容，支持视频、专栏、动态等"
)
async def bilibili_parse(_ctx: AgentCtx, url: str) -> str:
    """解析B站链接内容。

    自动识别并解析B站链接类型（视频、专栏、动态等），返回内容摘要。

    Args:
        url: B站链接，支持以下格式：
            - 视频链接: https://www.bilibili.com/video/BVxxx 或 avxxx
            - 动态链接: https://t.bilibili.com/xxx 或 dynamic/xxx
            - 专栏链接: https://www.bilibili.com/read/cvxxx
            - b23短链接: https://b23.tv/xxx

    Returns:
        str: 解析结果，包含内容类型、链接等信息。

    Example:
        bilibili_parse(url="https://www.bilibili.com/video/BV1xx")
        bilibili_parse(url="https://t.bilibili.com/123456")
    """
    if not config.api_url:
        return "错误: 未配置 BiliChat API 地址，请先在插件配置中设置"

    try:
        api = get_api()
        
        content = await api.parse_content(url)
        content_type = content.get("type", "unknown")
        content_id = content.get("id", "")
        b23_link = content.get("b23", "")
        
        type_names = {"video": "视频", "dynamic": "动态", "column": "专栏"}
        type_name = type_names.get(content_type, content_type)
        
        result = f"类型: {type_name}\n"
        result += f"ID: {content_id}\n"
        result += f"短链: {b23_link}"
        
        return result

    except Exception as e:
        plugin.logger.error(f"解析B站链接失败: {e}")
        return f"解析失败: {e}"


# =====================
# 沙盒方法 - UP主搜索
# =====================

@plugin.mount_sandbox_method(
    SandboxMethodType.TOOL,
    name="bilibili_search_up",
    description="搜索B站UP主"
)
async def bilibili_search_up(_ctx: AgentCtx, keyword: str, limit: int = 5) -> str:
    """搜索B站UP主。

    Args:
        keyword: 搜索关键词（UP主昵称或UID）。
        limit: 返回结果数量，默认5个，最多10个。

    Returns:
        str: 匹配的UP主列表。

    Example:
        bilibili_search_up(keyword="老番茄", limit=3)
    """
    if not config.api_url:
        return "错误: 未配置 BiliChat API 地址"

    try:
        api = get_api()
        limit = min(limit, 10)
        results = await api.search_up(keyword, limit)
        
        if not results:
            return f"未找到与 '{keyword}' 相关的UP主"
        
        lines = [f"找到 {len(results)} 位UP主:"]
        for up in results:
            lines.append(f"- {up['nickname']} (UID: {up['uid']})")
        
        return "\n".join(lines)

    except Exception as e:
        plugin.logger.error(f"搜索UP主失败: {e}")
        return f"搜索失败: {e}"


# =====================
# 沙盒方法 - 订阅管理
# =====================

@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    name="bilibili_subscribe",
    description="订阅B站UP主，获取其动态和直播推送"
)
async def bilibili_subscribe(_ctx: AgentCtx, keyword: str, nickname: str = "") -> str:
    """订阅B站UP主。

    Args:
        keyword: UP主昵称或UID。
        nickname: 自定义昵称（可选）。

    Returns:
        str: 订阅结果信息。

    Example:
        bilibili_subscribe(keyword="老番茄")
        bilibili_subscribe(keyword="546195", nickname="番茄")
    """
    if not config.api_url:
        return "错误: 未配置 BiliChat API 地址"

    try:
        api = get_api()
        results = await api.search_up(keyword, 1)
        
        if not results:
            return f"未找到UP主: {keyword}"
        
        up = results[0]
        uid = up["uid"]
        uname = up["nickname"]
        
        result = await SubscriptionManager.add_subscription(
            _ctx.from_chat_key, uid, uname, nickname
        )
        
        # 确保推送任务在运行
        if config.enable_push and not task.is_running("push_task", _ctx.from_chat_key):
            await task.start(
                task_type="push_task",
                task_id=_ctx.from_chat_key,
                chat_key=_ctx.from_chat_key,
                plugin=plugin,
                chat_key=_ctx.from_chat_key,
            )
        
        return result

    except Exception as e:
        plugin.logger.error(f"订阅失败: {e}")
        return f"订阅失败: {e}"


@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    name="bilibili_unsubscribe",
    description="取消订阅B站UP主"
)
async def bilibili_unsubscribe(_ctx: AgentCtx, keyword: str) -> str:
    """取消订阅B站UP主。

    Args:
        keyword: UP主昵称、UID或自定义昵称。使用 "all" 取消所有订阅。

    Returns:
        str: 取消订阅结果。

    Example:
        bilibili_unsubscribe(keyword="老番茄")
        bilibili_unsubscribe(keyword="all")
    """
    try:
        chat_key = _ctx.from_chat_key
        data = await SubscriptionManager.get_subscriptions(chat_key)
        
        if keyword.lower() in ("all", "全部"):
            count = len(data.ups)
            data.ups.clear()
            await SubscriptionManager.save_subscriptions(chat_key, data)
            
            # 停止推送任务
            if task.is_running("push_task", chat_key):
                await task.cancel("push_task", chat_key)
            
            return f"已取消所有订阅（共 {count} 位UP主）"
        
        if keyword.isdigit():
            uid = int(keyword)
            result = await SubscriptionManager.remove_subscription(chat_key, uid)
        else:
            for u, up in data.ups.items():
                if keyword in (up.uname, up.nickname) or str(u) == keyword:
                    result = await SubscriptionManager.remove_subscription(chat_key, u)
                    break
            else:
                return f"未找到UP主: {keyword}"
        
        # 如果没有订阅了，停止推送任务
        data = await SubscriptionManager.get_subscriptions(chat_key)
        if not data.ups and task.is_running("push_task", chat_key):
            await task.cancel("push_task", chat_key)
        
        return result

    except Exception as e:
        plugin.logger.error(f"取消订阅失败: {e}")
        return f"取消订阅失败: {e}"


@plugin.mount_sandbox_method(
    SandboxMethodType.TOOL,
    name="bilibili_list_subscriptions",
    description="查看当前会话的B站UP主订阅列表"
)
async def bilibili_list_subscriptions(_ctx: AgentCtx) -> str:
    """查看当前会话的B站UP主订阅列表。"""
    return await SubscriptionManager.list_subscriptions(_ctx.from_chat_key)


@plugin.mount_sandbox_method(
    SandboxMethodType.AGENT,
    name="bilibili_set_push_type",
    description="设置UP主推送方式"
)
async def bilibili_set_push_type(
    _ctx: AgentCtx, 
    keyword: str, 
    push_type: Literal["PUSH", "AT_ALL", "IGNORE"],
    content_type: Literal["all", "live", "dynamic"] = "all"
) -> str:
    """设置UP主推送方式。

    Args:
        keyword: UP主昵称、UID或自定义昵称。
        push_type: 推送方式：PUSH(正常推送)、AT_ALL(@全体)、IGNORE(不推送)
        content_type: 设置范围：all(全部)、live(仅直播)、dynamic(仅动态)

    Returns:
        str: 设置结果。

    Example:
        bilibili_set_push_type(keyword="老番茄", push_type="AT_ALL", content_type="live")
    """
    try:
        chat_key = _ctx.from_chat_key
        data = await SubscriptionManager.get_subscriptions(chat_key)
        
        uid = None
        if keyword.isdigit():
            uid = int(keyword)
        else:
            for u, up in data.ups.items():
                if keyword in (up.uname, up.nickname) or str(u) == keyword:
                    uid = u
                    break
        
        if uid is None or uid not in data.ups:
            return f"未找到UP主: {keyword}"
        
        return await SubscriptionManager.set_push_type(chat_key, uid, push_type, content_type)

    except Exception as e:
        plugin.logger.error(f"设置推送方式失败: {e}")
        return f"设置失败: {e}"


# =====================
# 沙盒方法 - 工具
# =====================

@plugin.mount_sandbox_method(
    SandboxMethodType.TOOL,
    name="bilibili_get_live_status",
    description="获取UP主直播状态"
)
async def bilibili_get_live_status(_ctx: AgentCtx, uid: int) -> str:
    """获取UP主直播状态。

    Args:
        uid: UP主的B站UID。

    Returns:
        str: 直播状态信息。

    Example:
        bilibili_get_live_status(uid=546195)
    """
    if not config.api_url:
        return "错误: 未配置 BiliChat API 地址"

    try:
        api = get_api()
        live = await api.get_live_status(uid)
        
        status_map = {0: "未开播", 1: "直播中", 2: "轮播中"}
        status = live.get("live_status", 0)
        
        result = f"UP主: {live.get('uname', '未知')} (UID: {uid})\n"
        result += f"直播状态: {status_map.get(status, '未知')}\n"
        
        if status == 1:
            result += f"标题: {live.get('title', '无标题')}\n"
            result += f"直播间: https://live.bilibili.com/{live.get('room_id')}\n"
            result += f"在线: {live.get('online', 0)}"
        
        return result

    except Exception as e:
        plugin.logger.error(f"获取直播状态失败: {e}")
        return f"获取失败: {e}"


@plugin.mount_sandbox_method(
    SandboxMethodType.TOOL,
    name="bilibili_b23_generate",
    description="生成B站b23短链接"
)
async def bilibili_b23_generate(_ctx: AgentCtx, url: str) -> str:
    """生成B站b23短链接。

    Args:
        url: B站长链接。

    Returns:
        str: 生成的b23短链接。

    Example:
        bilibili_b23_generate(url="https://www.bilibili.com/video/BV1xx")
    """
    if not config.api_url:
        return "错误: 未配置 BiliChat API 地址"

    try:
        api = get_api()
        b23 = await api.b23_generate(url)
        return f"短链接: {b23}"

    except Exception as e:
        plugin.logger.error(f"生成短链接失败: {e}")
        return f"生成失败: {e}"


# =====================
# 初始化与清理
# =====================

@plugin.mount_init_method()
async def init_plugin():
    """插件初始化"""
    plugin.logger.info(f"BiliChat 插件初始化中...")
    plugin.logger.info(f"API 地址: {config.api_url}")
    
    if config.api_url:
        try:
            api = get_api()
            if await api.check_health():
                plugin.logger.success("BiliChat API 连接正常")
            else:
                plugin.logger.warning("BiliChat API 连接失败，请检查配置")
        except Exception as e:
            plugin.logger.warning(f"BiliChat API 连接检查失败: {e}")
    
    plugin.logger.success("BiliChat 插件初始化完成")


@plugin.mount_cleanup_method()
async def cleanup_plugin():
    """插件清理"""
    plugin.logger.info("BiliChat 插件资源清理中...")
    
    # 停止所有推送任务
    await task.stop_all()
    
    # 关闭API客户端
    api = get_api()
    await api.close()
    
    plugin.logger.info("BiliChat 插件资源已清理")
