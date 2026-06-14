"""???????"""

from datetime import timedelta


def calc_time_total(t: float) -> str:
    """???????????????"""
    t_ms = int(t * 1000)
    if t_ms < 5000:
        return f"{t_ms} ??"
    total_seconds = t_ms // 1000
    td = timedelta(seconds=total_seconds)
    day = td.days
    hour = total_seconds // 3600 % 24
    mint = total_seconds // 60 % 60
    sec = total_seconds % 60
    parts = []
    if day:
        parts.append(f"{day} ?")
    if hour:
        parts.append(f"{hour} ??")
    if mint:
        parts.append(f"{mint} ??")
    if sec and not day and not hour:
        parts.append(f"{sec} ?")
    return " ".join(parts)


def format_live_start(up_name: str, title: str, room_id: int, at_all: bool = False, rich_media: bool = True) -> str:
    """?????????"""
    at_prefix = "[AT??] " if at_all else ""
    if rich_media:
        return f"{at_prefix}{up_name} ???: {title}\n[??]\nhttps://live.bilibili.com/{room_id}"
    return f"{at_prefix}{up_name} ???: {title}\nhttps://live.bilibili.com/{room_id}"


def format_live_end(up_name: str, live_time: float) -> str:
    """?????????"""
    time_str = calc_time_total(live_time)
    return f"{up_name} ???\n?????? {time_str}\n(????? bilibili ?????????????????)"


def format_dynamic(up_name: str, b23_link: str, at_all: bool = False, rich_media: bool = True) -> str:
    """?????????"""
    at_prefix = "[AT??] " if at_all else ""
    if rich_media:
        return f"{at_prefix}{up_name} ??????\n[??]\n{b23_link}"
    return f"{at_prefix}{up_name} ??????\n{b23_link}"
