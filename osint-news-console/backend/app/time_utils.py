"""统一使用“数据库内 UTC 无时区 + 展示时转换应用时区”的时间约定。"""

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from .config import get_config


def app_timezone() -> ZoneInfo:
    return ZoneInfo(get_config().timezone)


def utc_now() -> datetime:
    """返回适合 SQLite DateTime 存储的 UTC 无时区时间。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def as_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def as_local(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(app_timezone())


def local_day_bounds(target: date) -> tuple[datetime, datetime]:
    tz = app_timezone()
    start_local = datetime.combine(target, time.min, tzinfo=tz)
    end_local = datetime.combine(target, time.max, tzinfo=tz)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
    return aware.isoformat().replace("+00:00", "Z")
