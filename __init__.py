"""
NekroAgent BiliChat 插件

复刻 nonebot-plugin-bilichat 核心功能：
- 独立 YAML 订阅配置
- 定时轮询动态/直播
- 动态/直播推送
- 指令订阅管理（通过动态路由 API）
"""

import asyncio
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import httpx
import yaml
from deepdiff import DeepDiff
from fastapi import APIRouter, HTTPException, Query
from nekro_agent.api import message
from nekro_agent.api.plugin import ConfigBase, ExtraField, NekroPlugin
from nekro_agent.api.schemas import AgentCtx
from nekro_agent.services.plugin.task import AsyncTaskHandle, task
from pydantic import BaseModel, Field, computed_field

# 插件元信息
plugin = NekroPlugin(
    name="BiliChat",
    module_name="bilichat",
    description="B站UP主订阅推送插件，支持动态/直播推送、订阅管理",
    version="1.0.0",
    author="SevenNine233",
    url="https://github.com/SevenNine233/nekro_plugin_bilichat",
)


# =====================
# 数据模型
# =====================

class PushType(str, Enum):
    """推送方式"""
    AT_ALL = "AT_ALL"
    PUSH = "PUSH"
    IGNORE = "IGNORE"


class DynamicType(str, Enum):
    """动态类型"""
    DYNAMIC_TYPE_AD = "DYNAMIC_TYPE_AD"
    DYNAMIC_TYPE_APPLET = "DYNAMIC_TYPE_APPLET"
    DYNAMIC_TYPE_ARTICLE = "DYNAMIC_TYPE_ARTICLE"
    DYNAMIC_TYPE_AV = "DYNAMIC_TYPE_AV"
    DYNAMIC_TYPE_BANNER = "DYNAMIC_TYPE_BANNER"
    DYNAMIC_TYPE_COMMON_SQUARE = "DYNAMIC_TYPE_COMMON_SQUARE"
    DYNAMIC_TYPE_COMMON_VERTICAL = "DYNAMIC_TYPE_COMMON_VERTICAL"
    DYNAMIC_TYPE_COURSES = "DYNAMIC_TYPE_COURSES"
    DYNAMIC_TYPE_DRAW = "DYNAMIC_TYPE_DRAW"
    DYNAMIC_TYPE_FORWARD = "DYNAMIC_TYPE_FORWARD"
    DYNAMIC_TYPE_LIVE = "DYNAMIC_TYPE_LIVE"
    DYNAMIC_TYPE_LIVE_RCMD = "DYNAMIC_TYPE_LIVE_RCMD"
    DYNAMIC_TYPE_MEDIALIST = "DYNAMIC_TYPE_MEDIALIST"
    DYNAMIC_TYPE_MUSIC = "DYNAMIC_TYPE_MUSIC"
    DYNAMIC_TYPE_NONE = "DYNAMIC_TYPE_NONE"
    DYNAMIC_TYPE_PGC = "DYNAMIC_TYPE_PGC"
    DYNAMIC_TYPE_WORD = "DYNAMIC_TYPE_WORD"


# 忽略的动态类型
DYNAMIC_IGNORE_TYPE = {
    DynamicType.DYNAMIC_TYPE_AD,
    DynamicType.DYNAMIC_TYPE_LIVE,
    DynamicType.DYNAMIC_TYPE_LIVE_RCMD,
    DynamicType.DYNAMIC_TYPE_BANNER,
}

# 默认动态推送配置
DEFAULT_DYNAMIC_PUSH: Dict[DynamicType, PushType] = {
    t: (PushType.IGNORE if t in DYNAMIC_IGNORE_TYPE else PushType.PUSH)
    for t in DynamicType
}


class UP(BaseModel):
    """UP主信息"""
    uid: int = Field(..., description="UP主UID")
    uname: str = Field(default="", description="UP主B站用户名")
    nickname: str = Field(default="", description="自定义昵称")
    note: str = Field(default="", description="备注")
    dynamic: Dict[str, str] = Field(
        default_factory=lambda: {k.value: v.value for k, v in DEFAULT_DYNAMIC_PUSH.items()},
        description="各种类型动态推送方式"
    )
    live: PushType = Field(default=PushType.PUSH, description="直播推送方式")


class UserInfo(BaseModel):
    """用户订阅信息"""
    chat_key: str = Field(..., description="会话标识")
    subscribes: Dict[int, UP] = Field(default_factory=dict, description="订阅的UP主")

    def add_subscription(self, uid: int, uname: str, nickname: str = "") -> None:
        """添加订阅"""
        if uid in self.subscribes:
            self.subscribes[uid].uname = uname
            if nickname:
                self.subscribes[uid].nickname = nickname
        else:
            self.subscribes[uid] = UP(uid=uid, uname=uname, nickname=nickname)

    def remove_subscription(self, uid: int) -> bool:
        """移除订阅"""
        if uid in self.subscribes:
            del self.subscribes[uid]
            return True
        return False


class SubscribeConfig(BaseModel):
    """订阅配置"""
    dynamic_interval: int = Field(default=300, description="动态轮询间隔(秒)", ge=60)
    live_interval: int = Field(default=60, description="直播轮询间隔(秒)", ge=30)
    push_delay: int = Field(default=3, description="推送延迟(秒)", ge=0)
    use_rich_media: bool = Field(default=True, description="使用富媒体消息")
    users: Dict[str, UserInfo] = Field(default_factory=dict, description="用户订阅数据")


class ApiConfig(BaseModel):
    """API配置"""
    url: str = Field(default="http://192.168.0.102:40432", description="bilichat-request API地址")
    token: str = Field(default="", description="API Token")


class BiliChatConfigFile(BaseModel):
    """配置文件模型"""
    version: str = Field(default="1.0.0", description="配置版本")
    api: ApiConfig = Field(default_factory=ApiConfig, description="API配置")
    subs: SubscribeConfig = Field(default_factory=SubscribeConfig, description="订阅配置")


# =====================
# 配置管理器
# =====================

class ConfigManager:
    """配置管理器"""

    _config: BiliChatConfigFile = BiliChatConfigFile()
    _config_path: Optional[Path] = None

    @classmethod
    def get_config_path(cls) -> Path:
        """获取配置文件路径"""
        if cls._config_path is None:
            cls._config_path = plugin.get_plugin_data_dir() / "config.yaml"
        return cls._config_path

    @classmethod
    def get(cls) -> BiliChatConfigFile:
        """获取配置"""
        return cls._config

    @classmethod
    def load(cls) -> BiliChatConfigFile:
        """加载配置文件"""
        config_path = cls.get_config_path()
        
        if not config_path.exists():
            plugin.logger.info(f"[⚙️] 配置文件不存在，创建默认配置: {config_path}")
            cls._config = BiliChatConfigFile()
            cls.save()
            return cls._config
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            cls._config = BiliChatConfigFile.model_validate(data)
            plugin.logger.success(f"[✅] 配置文件加载成功")
            return cls._config
        except Exception as e:
            plugin.logger.error(f"[❌] 配置文件加载失败: {e}")
            cls._config = BiliChatConfigFile()
            return cls._config

    @classmethod
    def save(cls, log_diff: bool = True) -> None:
        """保存配置文件"""
        config_path = cls.get_config_path()
        
        # 获取旧配置用于比较
        old_config = None
        if log_diff and config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    old_data = yaml.safe_load(f) or {}
                old_config = BiliChatConfigFile.model_validate(old_data)
            except Exception:
                pass
        
        # 保存新配置
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(cls._config.model_dump(mode="json"), f, allow_unicode=True, indent=2)
        
        # 日志变更
        if log_diff and old_config:
            diff = DeepDiff(
                old_config.model_dump(mode="json"),
                cls._config.model_dump(mode="json"),
                ignore_order=True
            )
            if diff:
                if "values_changed" in diff:
                    for path, info in diff["values_changed"].items():
                        plugin.logger.info(f"[⚙️] 修改配置项 {path}: {info['old_value']} --> {info['new_value']}")
                if "dictionary_item_added" in diff:
                    for path in diff["dictionary_item_added"]:
                        plugin.logger.info(f"[🎉] 新增配置项: {path}")
                if "dictionary_item_removed" in diff:
                    for path in diff["dictionary_item_removed"]:
                        plugin.logger.info(f"[♻️] 移除配置项: {path}")
                plugin.logger.info("[💾] 配置已保存")

    @classmethod
    def set(cls, config: BiliChatConfigFile, log_diff: bool = True) -> None:
        """设置配置"""
        cls._config = config
        cls.save(log_diff)


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
        client = await self._get_client()
        try:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            raise Exception(f"API请求失败: {e.response.status_code}")
        except httpx.RequestError as e:
            raise Exception(f"网络错误: {e}")

    async def _get(self, url: str, **kwargs) -> Dict[str, Any]:
        return await self._request("GET", url, **kwargs)

    async def _post(self, url: str, **kwargs) -> Dict[str, Any]:
        return await self._request("POST", url, **kwargs)

    async def search_up(self, keyword: str, ps: int = 5) -> List[Dict[str, Any]]:
        """搜索UP主"""
        result = await self._get("/tools/search_up", params={"keyword": keyword, "ps": ps})
        return result if isinstance(result, list) else [result]

    async def get_live_status(self, uid: int) -> Dict[str, Any]:
        """获取直播状态"""
        return await self._get("/subs/live", params={"uid": uid})

    async def get_live_status_batch(self, uids: List[int]) -> List[Dict[str, Any]]:
        """批量获取直播状态"""
        return await self._post("/subs/lives", json=uids)

    async def get_dynamics(self, uid: int, offset: int = 0) -> List[Dict[str, Any]]:
        """获取动态列表"""
        return await self._get("/subs/dynamic", params={"uid": uid, "offset": offset})

    async def parse_dynamic(self, dynamic_id: str, quality: int = 75) -> Dict[str, Any]:
        """解析动态"""
        return await self._get("/content/dynamic", params={"dynamic_id": dynamic_id, "quality": quality})

    async def check_health(self) -> bool:
        """检查API健康状态"""
        try:
            await self._get("/version")
            return True
        except Exception:
            return False


def get_api() -> BiliChatAPI:
    """获取API客户端"""
    config = ConfigManager.get()
    return BiliChatAPI(config.api.url, config.api.token)


# =====================
# 推送状态
# =====================

class PushState:
    """推送状态管理"""
    dynamic_offsets: Dict[int, int] = {}  # {uid: last_dyn_id}
    live_status: Dict[int, int] = {}      # {uid: status}
    live_time: Dict[int, int] = {}        # {uid: timestamp}

    @classmethod
    def get_dynamic_offset(cls, uid: int) -> int:
        return cls.dynamic_offsets.get(uid, -1)

    @classmethod
    def set_dynamic_offset(cls, uid: int, offset: int) -> None:
        cls.dynamic_offsets[uid] = offset

    @classmethod
    def get_live_status(cls, uid: int) -> int:
        return cls.live_status.get(uid, -1)

    @classmethod
    def set_live_status(cls, uid: int, status: int, live_time: int = 0) -> None:
        cls.live_status[uid] = status
        cls.live_time[uid] = live_time

    @classmethod
    def get_live_time(cls, uid: int) -> int:
        return cls.live_time.get(uid, 0)


# =====================
# 推送任务
# =====================

async def push_message(chat_key: str, text: str) -> bool:
    """发送推送消息"""
    try:
        ctx = await AgentCtx.create_by_chat_key(chat_key)
        await message.send_text(chat_key, text, ctx)
        return True
    except Exception as e:
        plugin.logger.error(f"[❌] 推送失败 ({chat_key}): {e}")
        return False


async def check_dynamic():
    """检查动态"""
    plugin.logger.trace("[Dynamic] 检查新动态")
    config = ConfigManager.get()
    
    if not config.subs.users:
        return
    
    api = get_api()
    
    for chat_key, user in config.subs.users.items():
        for uid, up in user.subscribes.items():
            try:
                # 检查是否忽略所有动态
                if up.dynamic.get(DynamicType.DYNAMIC_TYPE_AV.value, PushType.PUSH.value) == PushType.IGNORE.value:
                    # 检查是否所有动态类型都设置为忽略
                    all_ignore = all(v == PushType.IGNORE.value for v in up.dynamic.values())
                    if all_ignore:
                        continue
                
                plugin.logger.debug(f"[Dynamic] 获取 UP {up.nickname or up.uname}({uid}) 动态")
                
                dynamics = await api.get_dynamics(uid)
                if not dynamics:
                    continue
                
                # 初始化偏移量
                if PushState.get_dynamic_offset(uid) == -1:
                    max_id = max(d["dyn_id"] for d in dynamics)
                    PushState.set_dynamic_offset(uid, max_id)
                    plugin.logger.info(f"[Dynamic] 初始化 UP {up.nickname or up.uname}({uid}) 动态偏移: {max_id}")
                    continue
                
                # 获取新动态
                last_offset = PushState.get_dynamic_offset(uid)
                new_dynamics = sorted(
                    [d for d in dynamics if d["dyn_id"] > last_offset],
                    key=lambda x: x["dyn_id"]
                )
                
                for dyn in new_dynamics:
                    dyn_type = dyn.get("dyn_type", "")
                    dyn_id = dyn["dyn_id"]
                    
                    # 检查是否忽略该类型
                    if up.dynamic.get(dyn_type, PushType.PUSH.value) == PushType.IGNORE.value:
                        plugin.logger.debug(f"[Dynamic] 忽略动态类型 {dyn_type}: {dyn_id}")
                        PushState.set_dynamic_offset(uid, dyn_id)
                        continue
                    
                    up_name = up.nickname or up.uname
                    plugin.logger.info(f"[Dynamic] UP {up_name}({uid}) 发布新动态: {dyn_id}")
                    
                    # 构建推送消息
                    b23 = ""
                    if config.subs.use_rich_media:
                        try:
                            content = await api.parse_dynamic(str(dyn_id), 75)
                            b23 = content.get("b23", "")
                        except Exception as e:
                            plugin.logger.warning(f"[Dynamic] 解析动态失败: {e}")
                    
                    push_type = up.dynamic.get(dyn_type, PushType.PUSH.value)
                    at_all = "@全体成员 " if push_type == PushType.AT_ALL.value else ""
                    
                    msg = f"{at_all}📺 {up_name} 发布了新动态\n"
                    if b23:
                        msg += f"{b23}"
                    else:
                        msg += f"https://t.bilibili.com/{dyn_id}"
                    
                    await push_message(chat_key, msg)
                    
                    # 更新偏移量
                    PushState.set_dynamic_offset(uid, dyn_id)
                    
                    # 推送延迟
                    if config.subs.push_delay > 0:
                        await asyncio.sleep(config.subs.push_delay)
                
            except Exception as e:
                plugin.logger.error(f"[Dynamic] 检查 UP {uid} 动态失败: {e}")


async def check_live():
    """检查直播"""
    plugin.logger.trace("[Live] 检查直播状态")
    config = ConfigManager.get()
    
    if not config.subs.users:
        return
    
    api = get_api()
    
    # 收集所有需要检查的UID
    all_uids = set()
    for user in config.subs.users.values():
        for uid, up in user.subscribes.items():
            if up.live != PushType.IGNORE:
                all_uids.add(uid)
    
    if not all_uids:
        return
    
    try:
        lives = await api.get_live_status_batch(list(all_uids))
        live_map = {lv["uid"]: lv for lv in lives}
    except Exception as e:
        plugin.logger.error(f"[Live] 获取直播状态失败: {e}")
        return
    
    for chat_key, user in config.subs.users.items():
        for uid, up in user.subscribes.items():
            if up.live == PushType.IGNORE:
                continue
            
            live = live_map.get(uid)
            if not live:
                continue
            
            live_status = live.get("live_status", 0)
            prev_status = PushState.get_live_status(uid)
            up_name = up.nickname or up.uname or live.get("uname", f"UID:{uid}")
            
            # 更新UP主名字
            if live.get("uname") and live["uname"] != up.uname:
                up.uname = live["uname"]
                ConfigManager.save(log_diff=False)
            
            # 初始化状态
            if prev_status == -1:
                PushState.set_live_status(uid, live_status, live.get("live_time", 0))
                plugin.logger.info(f"[Live] 初始化 UP {up_name}({uid}) 直播状态: {live_status}")
                continue
            
            try:
                # 开播通知
                if live_status == 1 and prev_status != 1:
                    title = live.get("title", "无标题")
                    room_id = live.get("room_id", "")
                    
                    at_all = "@全体成员 " if up.live == PushType.AT_ALL else ""
                    
                    msg = f"{at_all}🔴 {up_name} 开播了!\n"
                    msg += f"标题: {title}\n"
                    msg += f"直播间: https://live.bilibili.com/{room_id}"
                    
                    plugin.logger.info(f"[Live] UP {up_name}({uid}) 开播: {title}")
                    await push_message(chat_key, msg)
                
                # 下播通知
                elif live_status != 1 and prev_status == 1:
                    live_time = PushState.get_live_time(uid)
                    duration = ""
                    if live_time > 0:
                        elapsed = int(time.time() - live_time)
                        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
                        if h > 0:
                            duration = f"\n本次直播时长 {h}时{m}分{s}秒"
                        elif m > 0:
                            duration = f"\n本次直播时长 {m}分{s}秒"
                        else:
                            duration = f"\n本次直播时长 {s}秒"
                    
                    msg = f"⏹️ {up_name} 下播了{duration}"
                    
                    plugin.logger.info(f"[Live] UP {up_name}({uid}) 下播")
                    await push_message(chat_key, msg)
            
            finally:
                PushState.set_live_status(uid, live_status, live.get("live_time", 0))


@plugin.mount_async_task("push_loop")
async def push_loop_task(handle: AsyncTaskHandle):
    """推送轮询任务"""
    plugin.logger.info("[BiliChat] 推送任务启动")
    
    last_dynamic_check = 0
    last_live_check = 0
    
    while not handle.is_cancelled:
        try:
            config = ConfigManager.get()
            current_time = time.time()
            
            # 动态检查
            if current_time - last_dynamic_check >= config.subs.dynamic_interval:
                last_dynamic_check = current_time
                await check_dynamic()
            
            # 直播检查
            if current_time - last_live_check >= config.subs.live_interval:
                last_live_check = current_time
                await check_live()
            
            # 等待
            await asyncio.sleep(min(config.subs.dynamic_interval, config.subs.live_interval) // 4 + 10)
            
        except Exception as e:
            plugin.logger.error(f"[BiliChat] 推送任务异常: {e}")
            await asyncio.sleep(30)
    
    plugin.logger.info("[BiliChat] 推送任务停止")


# =====================
# 动态路由 API
# =====================

@plugin.mount_router()
def create_router() -> APIRouter:
    """创建 API 路由"""
    router = APIRouter()

    @router.get("/", summary="API 首页")
    async def api_home():
        """返回 API 基本信息"""
        return {
            "name": plugin.name,
            "version": plugin.version,
            "endpoints": [
                "GET / - API 首页",
                "GET /sub - 查看订阅列表",
                "POST /sub - 添加订阅",
                "DELETE /sub - 取消订阅",
                "PUT /push - 设置推送方式",
                "GET /live/{uid} - 查询直播状态",
            ]
        }

    @router.get("/sub", summary="查看订阅列表")
    async def get_subscriptions(
        chat_key: str = Query(..., description="会话标识")
    ):
        """查看指定会话的订阅列表"""
        config = ConfigManager.get()
        user = config.subs.users.get(chat_key)
        
        if not user or not user.subscribes:
            return {"chat_key": chat_key, "count": 0, "subscribes": []}
        
        subs = []
        for uid, up in user.subscribes.items():
            subs.append({
                "uid": uid,
                "uname": up.uname,
                "nickname": up.nickname,
                "live_push": up.live.value,
                "dynamic_push": up.dynamic.get(DynamicType.DYNAMIC_TYPE_AV.value, PushType.PUSH.value)
            })
        
        return {
            "chat_key": chat_key,
            "count": len(subs),
            "subscribes": subs
        }

    @router.post("/sub", summary="添加订阅")
    async def add_subscription(
        chat_key: str = Query(..., description="会话标识"),
        keyword: str = Query(..., description="UP主昵称或UID"),
        nickname: str = Query("", description="自定义昵称")
    ):
        """添加订阅"""
        config = ConfigManager.get()
        
        try:
            api = get_api()
            results = await api.search_up(keyword, 1)
            
            if not results:
                raise HTTPException(status_code=404, detail=f"未找到UP主: {keyword}")
            
            up_info = results[0]
            uid = up_info["uid"]
            uname = up_info["nickname"]
            
            # 添加订阅
            if chat_key not in config.subs.users:
                config.subs.users[chat_key] = UserInfo(chat_key=chat_key)
            
            config.subs.users[chat_key].add_subscription(uid, uname, nickname)
            ConfigManager.save()
            
            plugin.logger.info(f"[🎉] {chat_key} 订阅 UP {nickname or uname}({uid})")
            
            return {
                "success": True,
                "message": f"已订阅 UP {nickname or uname} (UID: {uid})",
                "uid": uid,
                "uname": uname,
                "nickname": nickname
            }
            
        except HTTPException:
            raise
        except Exception as e:
            plugin.logger.error(f"[❌] 添加订阅失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.delete("/sub", summary="取消订阅")
    async def remove_subscription(
        chat_key: str = Query(..., description="会话标识"),
        keyword: str = Query(..., description="UP主昵称、UID 或 'all'")
    ):
        """取消订阅"""
        config = ConfigManager.get()
        user = config.subs.users.get(chat_key)
        
        if not user:
            raise HTTPException(status_code=404, detail="该会话未订阅任何UP主")
        
        if keyword.lower() == "all":
            count = len(user.subscribes)
            user.subscribes.clear()
            ConfigManager.save()
            plugin.logger.info(f"[♻️] {chat_key} 取消全部订阅 ({count})")
            return {"success": True, "message": f"已取消全部订阅 ({count} 位UP主)"}
        
        # 查找UP主
        uid = None
        if keyword.isdigit():
            uid = int(keyword)
        else:
            for u, up in user.subscribes.items():
                if keyword in (up.uname, up.nickname) or str(u) == keyword:
                    uid = u
                    break
        
        if uid is None or uid not in user.subscribes:
            raise HTTPException(status_code=404, detail=f"未找到UP主: {keyword}")
        
        up = user.subscribes[uid]
        name = up.nickname or up.uname
        user.remove_subscription(uid)
        
        # 清理空用户
        if not user.subscribes:
            del config.subs.users[chat_key]
        
        ConfigManager.save()
        plugin.logger.info(f"[♻️] {chat_key} 取消订阅 {name}({uid})")
        
        return {"success": True, "message": f"已取消订阅 {name} (UID: {uid})"}

    @router.put("/push", summary="设置推送方式")
    async def set_push_type(
        chat_key: str = Query(..., description="会话标识"),
        keyword: str = Query(..., description="UP主昵称或UID"),
        push_type: PushType = Query(..., description="推送方式"),
        content_type: Literal["live", "dynamic", "all"] = Query("all", description="设置范围")
    ):
        """设置推送方式"""
        config = ConfigManager.get()
        user = config.subs.users.get(chat_key)
        
        if not user:
            raise HTTPException(status_code=404, detail="该会话未订阅任何UP主")
        
        # 查找UP主
        uid = None
        if keyword.isdigit():
            uid = int(keyword)
        else:
            for u, up in user.subscribes.items():
                if keyword in (up.uname, up.nickname) or str(u) == keyword:
                    uid = u
                    break
        
        if uid is None or uid not in user.subscribes:
            raise HTTPException(status_code=404, detail=f"未找到UP主: {keyword}")
        
        up = user.subscribes[uid]
        name = up.nickname or up.uname
        
        if content_type in ("all", "live"):
            up.live = push_type
        if content_type in ("all", "dynamic"):
            for dt in DynamicType:
                if dt not in DYNAMIC_IGNORE_TYPE:
                    up.dynamic[dt.value] = push_type.value
        
        ConfigManager.save()
        plugin.logger.info(f"[⚙️] {chat_key} 设置 {name}({uid}) 推送方式: {push_type.value} ({content_type})")
        
        return {
            "success": True,
            "message": f"已设置 {name} 的{content_type}推送方式为 {push_type.value}"
        }

    @router.get("/live/{uid}", summary="查询直播状态")
    async def get_live_status(uid: int):
        """查询UP主直播状态"""
        try:
            api = get_api()
            live = await api.get_live_status(uid)
            
            status_map = {0: "未开播", 1: "直播中", 2: "轮播中"}
            status = live.get("live_status", 0)
            
            result = {
                "uid": uid,
                "uname": live.get("uname", "未知"),
                "status": status,
                "status_text": status_map.get(status, "未知")
            }
            
            if status == 1:
                result["title"] = live.get("title", "无标题")
                result["room_id"] = live.get("room_id")
                result["online"] = live.get("online", 0)
                result["url"] = f"https://live.bilibili.com/{live.get('room_id')}"
            
            return result
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router


# =====================
# 初始化与清理
# =====================

@plugin.mount_init_method()
async def init_plugin():
    """插件初始化"""
    plugin.logger.info("[BiliChat] 插件初始化中...")
    
    # 加载配置
    config = ConfigManager.load()
    plugin.logger.info(f"[BiliChat] API 地址: {config.api.url}")
    
    # 检查API连接
    try:
        api = get_api()
        if await api.check_health():
            plugin.logger.success("[BiliChat] API 连接正常")
        else:
            plugin.logger.warning("[BiliChat] API 连接失败，请检查配置")
    except Exception as e:
        plugin.logger.warning(f"[BiliChat] API 连接检查失败: {e}")
    
    # 启动推送任务
    if config.subs.users:
        plugin.logger.info(f"[BiliChat] 发现 {len(config.subs.users)} 个会话的订阅数据，启动推送任务")
        if not task.is_running("push_loop", "main"):
            await task.start(
                task_type="push_loop",
                task_id="main",
                chat_key="system",
                plugin=plugin,
            )
    
    plugin.logger.success("[BiliChat] 插件初始化完成")


@plugin.mount_cleanup_method()
async def cleanup_plugin():
    """插件清理"""
    plugin.logger.info("[BiliChat] 插件资源清理中...")
    
    # 停止推送任务
    if task.is_running("push_loop", "main"):
        await task.cancel("push_loop", "main")
    
    # 关闭API客户端
    try:
        api = get_api()
        await api.close()
    except Exception:
        pass
    
    plugin.logger.info("[BiliChat] 插件资源已清理")
