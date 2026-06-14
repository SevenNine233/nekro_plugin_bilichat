"""nekro_plugin_bilichat - B站直播/动态推送插件

复刻 nonebot-plugin-bilichat 的核心功能：
- B站 UP 主直播开播/下播推送
- B站 UP 主动态更新推送
- WebUI 管理界面
- 命令：/bilichat sub, /bilichat unsub, /bilichat check, /bilichat atall
"""

from nekro_agent.core import logger
from nekro_agent.api.plugin import (
    ConfigBase,
    NekroPlugin,
    CommandGroup,
    CommandPermission,
    CmdCtl,
)
from nekro_agent.services.command.schemas import Arg, CommandExecutionContext

from pydantic import Field

from .models import PushType
from .subs_manager import SubsManager
from .api_client import BilichatAPI
from .polling import PollingService
from .webui import router as webui_router, set_subs_manager, set_config_data, ConfigData, register_config_handler

# ==================== 插件定义 ====================

plugin = NekroPlugin(
    name="B站推送插件",
    module_name="nekro_plugin_bilichat",
    description="提供 B站 UP 主直播开播/下播推送、动态更新推送，支持 WebUI 管理",
    version="1.0.0",
    author="NekroAgent",
    url="https://github.com/KroMiose/nekro-agent",
)


# 获取配置实例
config: BilichatConfig = plugin.get_config(BilichatConfig)


# ==================== 全局实例 ====================

subs_manager = SubsManager()
api_client = BilichatAPI(
    base_url=config.API_URL,
    token=config.API_TOKEN,
)
polling_service = PollingService(
    api=api_client,
    subs=subs_manager,
    config={
        "live_interval": config.LIVE_INTERVAL,
        "dynamic_interval": config.DYNAMIC_INTERVAL,
        "browser_shot_quality": config.BROWSER_SHOT_QUALITY,
        "use_rich_media": config.USE_RICH_MEDIA,
    },
)

# 注入到 WebUI
set_subs_manager(subs_manager)
set_config_data(ConfigData(
    api_url=config.API_URL,
    api_token=config.API_TOKEN,
    live_interval=config.LIVE_INTERVAL,
    dynamic_interval=config.DYNAMIC_INTERVAL,
    browser_shot_quality=config.BROWSER_SHOT_QUALITY,
    use_rich_media=config.USE_RICH_MEDIA,
))


# ==================== 命令定义 ====================

bilichat_group = plugin.mount_command_group(
    name="bilichat",
    description="B站推送管理命令组",
    permission=CommandPermission.ADVANCED,
)


@bilichat_group.command(
    name="sub",
    description="订阅 UP 主",
    usage="/bilichat sub <UP名称>",
)
async def cmd_sub(context: CommandExecutionContext, raw_args: str = Arg(greedy=True, default="")):
    """订阅 UP 主"""
    keyword = raw_args.strip()
    if not keyword:
        return CmdCtl.failed("请输入 UP 主的名称，例如：/bilichat sub 泠鸢yousa")

    results = await api_client.search_up(keyword)
    if not results:
        return CmdCtl.failed(f"??? UP: {keyword}")

    if len(results) == 1:
        up = results[0]
    else:
        # ?????????
        up_list = "\n".join([f"  • {u.nickname}({u.uid})" for u in results[:5]])
        return CmdCtl.success(f"?????? UP \"{keyword}\", ????:\n{up_list}\n\n??? UID ?????/bilichat sub <UID>")

    # ????
    chat_key = context.chat_key
    subs_manager.add_subscription(chat_key, up.uid, up.nickname)
    logger.info(f"[Bilichat] ?? {chat_key} ??? UP {up.nickname}({up.uid})")
    return CmdCtl.success(f"??? UP {up.nickname}({up.uid})")
@bilichat_group.command(
    name="unsub",
    description="取消订阅 UP 主",
    usage="/bilichat unsub <UP名称/UID> 或 /bilichat unsub all",
)
async def cmd_unsub(context: CommandExecutionContext, raw_args: str = Arg(greedy=True, default="")):
    """取消订阅 UP 主"""
    keyword = raw_args.strip().lower()
    if not keyword:
        return CmdCtl.failed("请输入要取消的 UP 名称或 UID，使用 /bilichat unsub all 取消全部")

    chat_key = context.chat_key

    if keyword in ("all", "全部"):
        count = subs_manager.remove_all_subscriptions(chat_key)
        return CmdCtl.success(f"已取消本频道全部 {count} 个 UP 订阅")

    # 通过关键词查找
    up = subs_manager.get_up_by_keyword(chat_key, keyword)
    if not up:
        # 尝试通过 UID 直接查找
        try:
            uid = int(keyword.replace("uid:", "").strip())
            up = subs_manager.get_up(chat_key, uid)
        except ValueError:
            pass

    if not up:
        return CmdCtl.failed(f"未找到订阅: {keyword}，使用 /bilichat check 查看当前订阅列表")

    subs_manager.remove_subscription(chat_key, up.uid)
    up_name = up.nickname or up.uname
    logger.info(f"[Bilichat] 频道 {chat_key} 取消订阅 UP {up_name}({up.uid})")
    return CmdCtl.success(f"已取消订阅 UP {up_name}({up.uid})")


@bilichat_group.command(
    name="check",
    description="查看当前频道订阅列表",
    usage="/bilichat check",
)
async def cmd_check(context: CommandExecutionContext, raw_args: str = Arg(greedy=True, default="")):
    """查看订阅列表"""
    chat_key = context.chat_key
    subs = subs_manager.get_subscriptions(chat_key)
    if not subs:
        return CmdCtl.success("当前频道暂无 UP 订阅")

    lines = [f"当前频道共订阅 {len(subs)} 个 UP:"]
    for i, up in enumerate(subs.values()):
        name = up.nickname or up.uname
        lines.append(f"  {i + 1}. {name}({up.uid})")
    return CmdCtl.success("\n".join(lines))


@bilichat_group.command(
    name="atall",
    description="设置 UP 的 AT 全体",
    usage="/bilichat atall <UP名称> <live|动态类型> <on|off>",
)
async def cmd_atall(context: CommandExecutionContext, raw_args: str = Arg(greedy=True, default="")):
    """设置 AT 全体"""
    parts = raw_args.strip().split()
    if len(parts) != 3:
        return CmdCtl.failed(
            "用法：/bilichat atall <UP名称> <live|动态类型> <on|off>\n"
            "例如：/bilichat atall 泠鸢yousa live on"
        )

    keyword = parts[0]
    target = parts[1]
    action = parts[2]

    chat_key = context.chat_key

    # 查找 UP
    up = subs_manager.get_up_by_keyword(chat_key, keyword)
    if not up:
        try:
            uid = int(keyword.replace("uid:", "").strip())
            up = subs_manager.get_up(chat_key, uid)
        except ValueError:
            pass

    if not up:
        return CmdCtl.failed(f"未找到订阅: {keyword}")

    push_type = PushType.AT_ALL if action.lower() == "on" else PushType.PUSH
    up_name = up.nickname or up.uname

    subs_manager.set_at_all(chat_key, up.uid, target, push_type)
    target_name = "直播" if target == "live" else f"动态类型 {target}"
    status = "开启" if push_type == PushType.AT_ALL else "关闭"
    return CmdCtl.success(f"已为 UP {up_name}({up.uid}) 的 {target_name} {status} AT 全体")


# ==================== 初始化与路由 ====================

@plugin.mount_init_method()
async def init():
    """?????"""
    logger.info("[Bilichat] ?????...")

    # ???????????????????
    subs_manager.load()

    # ??? WebUI
    set_subs_manager(subs_manager)
    set_config_data(ConfigData(
        api_url=config.API_URL,
        api_token=config.API_TOKEN,
        live_interval=config.LIVE_INTERVAL,
        dynamic_interval=config.DYNAMIC_INTERVAL,
        browser_shot_quality=config.BROWSER_SHOT_QUALITY,
        use_rich_media=config.USE_RICH_MEDIA,
    ))

    # ?????????WebUI ??????????
    def on_config_change(cfg: ConfigData):
        global api_client
        api_client = BilichatAPI(base_url=cfg.api_url, token=cfg.api_token)
        polling_service._config.update({
            "live_interval": cfg.live_interval,
            "dynamic_interval": cfg.dynamic_interval,
            "browser_shot_quality": cfg.browser_shot_quality,
            "use_rich_media": cfg.use_rich_media,
        })
    register_config_handler(on_config_change)

    logger.info(f"[Bilichat] ??? {len(subs_manager.get_all_subscribed_uids())} ? UP ??")
    await polling_service.start()
    logger.info("[Bilichat] ?????")

@plugin.mount_cleanup_method()
async def cleanup():
    """插件清理"""
    logger.info("[Bilichat] 插件清理中...")
    await polling_service.stop()
    await api_client.close()
    logger.info("[Bilichat] 插件已清理")


@plugin.mount_router()
def create_bilichat_router():
    """挂载 WebUI 路由"""
    return webui_router
