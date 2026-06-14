"""订阅管理 - JSON 文件持久化"""

import json
import os
from pathlib import Path
from typing import Optional

from .models import PushType, UP, UPStatus, SubscriptionsData, DEFAULT_DYNAMIC_PUSH_TYPE, DynamicType

# 数据目录：使用环境变量 DATA_DIR + 插件子目录
DATA_DIR = os.environ.get("DATA_DIR", "./data/nekro_agent")
SUBS_DIR = Path(DATA_DIR) / "plugins" / "nekro_plugin_bilichat"
SUBS_FILE = SUBS_DIR / "subscriptions.json"


class SubsManager:
    """订阅管理器"""

    def __init__(self):
        self._data: SubscriptionsData = SubscriptionsData()
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            self.load()

    def load(self):
        """从 JSON 文件加载订阅数据"""
        SUBS_DIR.mkdir(parents=True, exist_ok=True)
        if SUBS_FILE.exists():
            try:
                with open(SUBS_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self._data = SubscriptionsData.model_validate(raw)
            except Exception:
                self._data = SubscriptionsData()
        else:
            self._data = SubscriptionsData()
        self._loaded = True

    def save(self):
        """保存订阅数据到 JSON 文件"""
        SUBS_DIR.mkdir(parents=True, exist_ok=True)
        with open(SUBS_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data.model_dump(), f, ensure_ascii=False, indent=2)

    # --- 订阅管理 ---

    def add_subscription(self, chat_key: str, uid: int, uname: str) -> UP:
        """为指定频道添加 UP 订阅"""
        self._ensure_loaded()
        if chat_key not in self._data.subscriptions:
            self._data.subscriptions[chat_key] = {}
        up = UP(uid=uid, uname=uname)
        self._data.subscriptions[chat_key][uid] = up
        # 初始化运行时状态
        if uid not in self._data.up_statuses:
            self._data.up_statuses[uid] = UPStatus(uid=uid, name=uname)
        self.save()
        return up

    def remove_subscription(self, chat_key: str, uid: int) -> bool:
        """为指定频道移除 UP 订阅"""
        self._ensure_loaded()
        if chat_key not in self._data.subscriptions:
            return False
        if uid not in self._data.subscriptions[chat_key]:
            return False
        del self._data.subscriptions[chat_key][uid]
        # 清理空频道
        if not self._data.subscriptions[chat_key]:
            del self._data.subscriptions[chat_key]
        self.save()
        return True

    def remove_all_subscriptions(self, chat_key: str) -> int:
        """移除指定频道所有订阅，返回移除数量"""
        self._ensure_loaded()
        if chat_key not in self._data.subscriptions:
            return 0
        count = len(self._data.subscriptions[chat_key])
        del self._data.subscriptions[chat_key]
        self.save()
        return count

    def get_subscriptions(self, chat_key: str) -> dict[int, UP]:
        """获取指定频道的所有订阅"""
        self._ensure_loaded()
        return self._data.subscriptions.get(chat_key, {})

    def get_up(self, chat_key: str, uid: int) -> UP | None:
        """获取指定频道中某个 UP 的订阅"""
        self._ensure_loaded()
        return self._data.subscriptions.get(chat_key, {}).get(uid)

    def get_up_by_keyword(self, chat_key: str, keyword: str) -> UP | None:
        """通过关键词（昵称/UID/用户名）查找 UP"""
        self._ensure_loaded()
        subs = self._data.subscriptions.get(chat_key, {})
        for up in subs.values():
            if keyword in (up.uname, up.nickname) or str(up.uid) == keyword.lower().replace("uid:", "").strip():
                return up
        return None

    def update_up(self, chat_key: str, up: UP):
        """更新 UP 订阅信息"""
        self._ensure_loaded()
        if chat_key not in self._data.subscriptions:
            self._data.subscriptions[chat_key] = {}
        self._data.subscriptions[chat_key][up.uid] = up
        self.save()

    def set_at_all(self, chat_key: str, uid: int, target: str, push_type: PushType):
        """设置某 UP 的 AT 全体"""
        self._ensure_loaded()
        up = self._data.subscriptions.get(chat_key, {}).get(uid)
        if not up:
            raise ValueError(f"未找到 UP {uid} 的订阅")
        if target == "live":
            up.live = push_type
        else:
            try:
                dyn_type = DynamicType(target)
            except ValueError:
                raise ValueError(f"???????: {target}") from None
            up.dynamic[dyn_type] = push_type
        self.save()

    # --- 运行时状态 ---

    def get_up_status(self, uid: int) -> UPStatus:
        """获取 UP 运行时状态"""
        self._ensure_loaded()
        if uid not in self._data.up_statuses:
            self._data.up_statuses[uid] = UPStatus(uid=uid, name="")
        return self._data.up_statuses[uid]

    def update_up_status(self, status: UPStatus):
        """更新 UP 运行时状态"""
        self._ensure_loaded()
        self._data.up_statuses[status.uid] = status
        self.save()

    # --- 全局查询 ---

    def get_all_subscribed_uids(self) -> set[int]:
        """获取所有已订阅的 UP UID 集合"""
        self._ensure_loaded()
        uids: set[int] = set()
        for chat_subs in self._data.subscriptions.values():
            uids.update(chat_subs.keys())
        return uids

    def get_chat_keys_for_up(self, uid: int) -> list[str]:
        """获取订阅了某 UP 的所有频道"""
        self._ensure_loaded()
        chat_keys: list[str] = []
        for chat_key, subs in self._data.subscriptions.items():
            if uid in subs:
                chat_keys.append(chat_key)
        return chat_keys

    def get_all_data(self) -> SubscriptionsData:
        """获取完整数据（供 WebUI 使用）"""
        self._ensure_loaded()
        return self._data
