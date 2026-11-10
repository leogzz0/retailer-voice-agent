"""Single source of 'now'. Everything date-sensitive (seed, 'hoy/mañana', cutoffs) uses this,
so tests and demos can pin time with NOPALIA_FROZEN_NOW and never flake at midnight."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from nopalia_api.config import get_settings


def business_tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def now_local() -> datetime:
    frozen = get_settings().frozen_now
    if frozen is not None:
        return frozen.astimezone(business_tz())
    return datetime.now(business_tz())


def today_local() -> date:
    return now_local().date()
