"""数据模型定义 - 订阅、推送类型、动态类型"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class PushType(str, Enum):
    """推送方式"""
    AT_ALL = "AT_ALL"
    PUSH = "PUSH"
    IGNORE = "IGNORE"


class DynamicType(str, Enum):
    """B站动态类型"""
    DYNAMIC_TYPE_AD = "DYNAMIC_TYPE_AD"
    DYNAMIC_TYPE_APPLET = "DYNAMIC_TYPE_APPLET"
    DYNAMIC_TYPE_ARTICLE = "DYNAMIC_TYPE_ARTICLE"
    DYNAMIC_TYPE_AV = "DYNAMIC_TYPE_AV"
    DYNAMIC_TYPE_BANNER = "DYNAMIC_TYPE_BANNER"
    DYNAMIC_TYPE_COMMON_SQUARE = "DYNAMIC_TYPE_COMMON_SQUARE"
    DYNAMIC_TYPE_COMMON_VERTICAL = "DYNAMIC_TYPE_COMMON_VERTICAL"
    DYNAMIC_TYPE_COURSES = "DYNAMIC_TYPE_COURSES"
    DYNAMIC_TYPE_COURSES_BATCH = "DYNAMIC_TYPE_COURSES_BATCH"
    DYNAMIC_TYPE_COURSES_SEASON = "DYNAMIC_TYPE_COURSES_SEASON"
    DYNAMIC_TYPE_DRAW = "DYNAMIC_TYPE_DRAW"
    DYNAMIC_TYPE_FORWARD = "DYNAMIC_TYPE_FORWARD"
    DYNAMIC_TYPE_LIVE = "DYNAMIC_TYPE_LIVE"
    DYNAMIC_TYPE_LIVE_RCMD = "DYNAMIC_TYPE_LIVE_RCMD"
    DYNAMIC_TYPE_MEDIALIST = "DYNAMIC_TYPE_MEDIALIST"
    DYNAMIC_TYPE_MUSIC = "DYNAMIC_TYPE_MUSIC"
    DYNAMIC_TYPE_NONE = "DYNAMIC_TYPE_NONE"
    DYNAMIC_TYPE_PGC = "DYNAMIC_TYPE_PGC"
    DYNAMIC_TYPE_SUBSCRIPTION = "DYNAMIC_TYPE_SUBSCRIPTION"
    DYNAMIC_TYPE_SUBSCRIPTION_NEW = "DYNAMIC_TYPE_SUBSCRIPTION_NEW"
    DYNAMIC_TYPE_UGC_SEASON = "DYNAMIC_TYPE_UGC_SEASON"
    DYNAMIC_TYPE_WORD = "DYNAMIC_TYPE_WORD"


# 默认忽略的动态类型（广告、直播分享等）
DYNAMIC_IGNORE_TYPES = {
    DynamicType.DYNAMIC_TYPE_AD,
    DynamicType.DYNAMIC_TYPE_LIVE,
    DynamicType.DYNAMIC_TYPE_LIVE_RCMD,
    DynamicType.DYNAMIC_TYPE_BANNER,
}

# 默认各类型推送方式
DEFAULT_DYNAMIC_PUSH_TYPE: dict[DynamicType, PushType] = {
    t: (PushType.IGNORE if t in DYNAMIC_IGNORE_TYPES else PushType.PUSH)
    for t in DynamicType
}


class UP(BaseModel):
    """UP 主订阅信息"""
    uid: int
    """UP 主 UID"""
    uname: str = ""
    """UP 主 B站用户名"""
    nickname: str = ""
    """UP 主昵称（可自定义）"""
    note: str = ""
    """备注"""
    dynamic: dict[DynamicType, PushType] = Field(default_factory=DEFAULT_DYNAMIC_PUSH_TYPE.copy)
    """各类型动态推送方式"""
    live: PushType = PushType.PUSH
    """直播推送方式"""


class UPStatus(BaseModel):
    """UP 主运行时状态（用于轮询比对）"""
    uid: int
    name: str
    dyn_offset: int = -1
    live_status: int = -1
    live_time: int = 0


class SubscriptionsData(BaseModel):
    """全局订阅数据存储结构 {chat_key: {uid: UP}}"""
    subscriptions: dict[str, dict[int, UP]] = Field(default_factory=dict)
    up_statuses: dict[int, UPStatus] = Field(default_factory=dict)


# --- bilichat-request API 响应模型 ---

class Dynamic(BaseModel):
    """动态信息"""
    dyn_id: int
    dyn_timestamp: int
    dyn_type: DynamicType


class LiveRoom(BaseModel):
    """直播房间信息"""
    uid: int
    uname: str = ""
    title: str = ""
    room_id: int = 0
    live_status: int = 0
    live_time: int = 0
    cover_from_user: str = ""
    online: int = 0
    area_name: str = ""
    face: str = ""
    keyframe: str = ""


class Content(BaseModel):
    """内容截图"""
    type: str  # "video", "column", "dynamic"
    id: str
    b23: str
    img: str  # base64


class SearchUp(BaseModel):
    """搜索 UP 结果"""
    nickname: str
    uid: int
