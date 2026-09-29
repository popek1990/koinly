"""Time zones for Koinly files.

A Koinly file has no offset in its dates. Koinly reads them as UTC unless you pick another
zone in the import dialog (help articles 9489985 and 9490014). So the zone a file is written
in and the zone chosen at import must be the same.
"""
from __future__ import annotations

from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .model import DataError

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_ACCEPTED_FORMATS = (DATE_FORMAT, "%Y-%m-%d %H:%M")


def get_zone(name: str) -> tzinfo:
    if name.upper() == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise DataError(f"unknown time zone {name!r} (use an IANA name such as Europe/London)") from None


def zone_name(zone: tzinfo) -> str:
    return "UTC" if zone is timezone.utc else str(zone)


def format_local(moment: datetime, zone: tzinfo) -> str:
    return moment.astimezone(zone).strftime(DATE_FORMAT)


def local_time_problem(naive: datetime, zone: tzinfo) -> str | None:
    """Detect wall-clock times that a zone with daylight saving cannot represent exactly.

    "ambiguous": the time happens twice (clocks go back), so the file does not say which one.
    "nonexistent": the time is skipped (clocks go forward).
    """
    if zone is timezone.utc:
        return None
    first = naive.replace(tzinfo=zone, fold=0)
    second = naive.replace(tzinfo=zone, fold=1)
    if first.utcoffset() == second.utcoffset():
        return None
    back = first.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
    return "nonexistent" if back != naive else "ambiguous"


def parse_local(text: str, zone: tzinfo) -> datetime:
    """Parse a Koinly-style date written in `zone`; return an aware UTC datetime."""
    text = text.strip()
    for fmt in _ACCEPTED_FORMATS:
        try:
            naive = datetime.strptime(text, fmt)
            break
        except ValueError:
            continue
    else:
        raise DataError(f"date {text!r} is not in the form YYYY-MM-DD HH:mm:ss")
    problem = local_time_problem(naive, zone)
    if problem == "nonexistent":
        raise DataError(f"date {text!r} does not exist in {zone_name(zone)} (clocks went forward)")
    return naive.replace(tzinfo=zone).astimezone(timezone.utc)


def parse_export_time(text: str, zone: tzinfo = timezone.utc) -> datetime:
    """Parse a timestamp from an export or an API: plain, ISO 8601, with or without offset."""
    text = text.strip()
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise DataError(f"cannot read timestamp {text!r}") from None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone)
    return moment.astimezone(timezone.utc).replace(microsecond=0)
