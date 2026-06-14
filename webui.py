"""WebUI 管理界面 - FastAPI router + 静态页面"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from .subs_manager import SubsManager
from .models import PushType, UP, SubscriptionsData

router = APIRouter(prefix="/bilichat", tags=["Bilichat WebUI"])


# --- 请求/响应模型 ---

class AddSubRequest(BaseModel):
    chat_key: str
    uid: int
    uname: str


class RemoveSubRequest(BaseModel):
    chat_key: str
    uid: int


class SetAtAllRequest(BaseModel):
    chat_key: str
    uid: int
    target: str = "live"  # "live" or dynamic type
    push_type: PushType


class ConfigData(BaseModel):
    api_url: str = "http://192.168.1.102:40432"
    api_token: str = ""
    live_interval: int = 60
    dynamic_interval: int = 300
    browser_shot_quality: int = 75
    use_rich_media: bool = True


# 全局引用，在 __init__.py 中注入
_subs_manager: SubsManager | None = None
_config_data: ConfigData = ConfigData()
_config_change_handlers: list = []


def register_config_handler(handler):
    """注册配置变更回调，回调接受 ConfigData 参数"""
    _config_change_handlers.append(handler)


def set_subs_manager(mgr: SubsManager):
    global _subs_manager
    _subs_manager = mgr


def get_subs_manager() -> SubsManager:
    if _subs_manager is None:
        raise HTTPException(500, "订阅管理器未初始化")
    return _subs_manager


def set_config_data(cfg: ConfigData):
    global _config_data
    _config_data = cfg


def get_config_data() -> ConfigData:
    return _config_data


# --- API 端点 ---

@router.get("/api/subscriptions")
async def list_subscriptions():
    """列出所有订阅"""
    mgr = get_subs_manager()
    data = mgr.get_all_data()
    result = {}
    for chat_key, ups in data.subscriptions.items():
        result[chat_key] = [up.model_dump() for up in ups.values()]
    return JSONResponse(result)


@router.post("/api/subscriptions/add")
async def add_subscription(req: AddSubRequest):
    """添加订阅"""
    mgr = get_subs_manager()
    up = mgr.add_subscription(req.chat_key, req.uid, req.uname)
    return JSONResponse({"success": True, "up": up.model_dump()})


@router.post("/api/subscriptions/remove")
async def remove_subscription(req: RemoveSubRequest):
    """移除订阅"""
    mgr = get_subs_manager()
    ok = mgr.remove_subscription(req.chat_key, req.uid)
    return JSONResponse({"success": ok})


@router.post("/api/subscriptions/atall")
async def set_at_all(req: SetAtAllRequest):
    """设置 AT 全体"""
    mgr = get_subs_manager()
    mgr.set_at_all(req.chat_key, req.uid, req.target, req.push_type)
    return JSONResponse({"success": True})


@router.get("/api/config")
async def get_config():
    """获取配置"""
    cfg = get_config_data()
    return JSONResponse(cfg.model_dump())


@router.post("/api/config")
async def set_config(cfg: ConfigData):
    """更新配置"""
    set_config_data(cfg)
    for handler in _config_change_handlers:
        handler(cfg)
    return JSONResponse({"success": True, "config": cfg.model_dump()})


@router.get("/api/status")
async def get_status():
    """获取状态"""
    mgr = get_subs_manager()
    data = mgr.get_all_data()
    statuses = {}
    for uid, status in data.up_statuses.items():
        statuses[str(uid)] = status.model_dump()
    return JSONResponse({
        "total_ups": len(data.up_statuses),
        "total_chats": len(data.subscriptions),
        "statuses": statuses,
    })


# --- 静态页面 ---

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "webui.html"


@router.get("/", response_class=HTMLResponse)
@router.get("", response_class=HTMLResponse)
async def serve_webui():
    """返回管理界面"""
    if not _TEMPLATE_PATH.exists():
        return HTMLResponse(content="<h1>模板文件未找到</h1>", status_code=500)
    html_content = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return HTMLResponse(content=html_content)
