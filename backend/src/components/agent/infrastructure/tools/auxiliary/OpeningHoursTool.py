"""OpeningHoursTool — OSM `opening_hours` parser and planner filter.

The tool consumes the `opening_hours` tag already extracted by OverpassClient
(see OverpassClient._parse_element). It supports the most common real-world
patterns used by tourist POIs:

    - `24/7`
    - `Mo-Fr 09:00-18:00`
    - `Mo,We,Fr 10:00-20:00`
    - `Mo-Su 10:00-22:00; PH off`
    - `Sa-Su 11:00-19:00`
    - multi-rule strings separated by `;` or `,`

The goal is not to cover the full OSM spec — that would require a dedicated
library. We correctly handle the patterns that make up the overwhelming
majority of tag values on tourist objects and return `None` for unparseable
strings so the caller can fall back to treating the POI as "always open"
instead of incorrectly filtering it out.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# OSM uses 2-letter English codes for weekdays.
_WEEKDAY_CODES: Tuple[str, ...] = ('Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su')
_CODE_INDEX: Dict[str, int] = {code: idx for idx, code in enumerate(_WEEKDAY_CODES)}


@dataclass(frozen=True)
class OpeningInterval:
    """One opening window on a specific weekday (0=Mo, 6=Su)."""

    weekday: int
    start: time
    end: time
    overnight: bool = False  # end <= start means the window crosses midnight


@dataclass(frozen=True)
class ParsedOpeningHours:
    intervals: Tuple[OpeningInterval, ...]
    # Raw source for debugging / logging.
    source: str


def _expand_weekdays(spec: str) -> List[int]:
    """Expand `Mo`, `Mo-Fr`, `Mo,We,Fr` into explicit weekday indices."""
    out: List[int] = []
    for chunk in spec.split(','):
        chunk = chunk.strip()
        if not chunk:
            continue
        if '-' in chunk:
            a, b = chunk.split('-', 1)
            a = a.strip()
            b = b.strip()
            if a not in _CODE_INDEX or b not in _CODE_INDEX:
                raise ValueError(f'unknown weekday range: {chunk}')
            start = _CODE_INDEX[a]
            end = _CODE_INDEX[b]
            if end >= start:
                out.extend(range(start, end + 1))
            else:
                # Wrap-around (e.g. Fr-Mo).
                out.extend(range(start, 7))
                out.extend(range(0, end + 1))
        else:
            if chunk not in _CODE_INDEX:
                raise ValueError(f'unknown weekday: {chunk}')
            out.append(_CODE_INDEX[chunk])
    return out


def _parse_time_range(spec: str) -> Tuple[time, time]:
    """Parse `09:00-18:00` into `(time(9,0), time(18,0))`."""
    if '-' not in spec:
        raise ValueError(f'not a time range: {spec}')
    a, b = spec.split('-', 1)
    return _parse_hhmm(a.strip()), _parse_hhmm(b.strip())


def _parse_hhmm(spec: str) -> time:
    if spec == '24:00':
        return time(23, 59)
    parts = spec.split(':')
    if len(parts) != 2:
        raise ValueError(f'not hh:mm: {spec}')
    hh, mm = int(parts[0]), int(parts[1])
    if hh == 24 and mm == 0:
        return time(23, 59)
    return time(hh, mm)


_RULE_TOKEN_RE = re.compile(
    r'^(?P<days>(?:Mo|Tu|We|Th|Fr|Sa|Su|PH|SH|off)(?:\s*[-,]\s*(?:Mo|Tu|We|Th|Fr|Sa|Su))*)'
    r'(?:\s+(?P<times>[0-9]{1,2}:[0-9]{2}\s*-\s*[0-9]{1,2}:[0-9]{2}'
    r'(?:\s*,\s*[0-9]{1,2}:[0-9]{2}\s*-\s*[0-9]{1,2}:[0-9]{2})*))?'
    r'(?P<closed>\s+(?:off|closed))?\s*$'
)


def parse_opening_hours(raw: Optional[str]) -> Optional[ParsedOpeningHours]:
    """Parse an OSM `opening_hours` tag.

    Returns `None` when the input is empty or cannot be parsed. Callers should
    treat `None` as "no information" rather than "closed".
    """
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text in {'24/7', '00:00-24:00'}:
        intervals = tuple(
            OpeningInterval(weekday=i, start=time(0, 0), end=time(23, 59))
            for i in range(7)
        )
        return ParsedOpeningHours(intervals=intervals, source=raw)

    intervals: List[OpeningInterval] = []
    # Rules are separated by `;` in the OSM spec.
    for rule in (r.strip() for r in text.split(';') if r.strip()):
        # Skip public/school-holiday rules — we don't have a holiday calendar.
        if rule.startswith('PH') or rule.startswith('SH'):
            continue
        match = _RULE_TOKEN_RE.match(rule)
        if not match:
            logger.debug('opening_hours: unparseable rule %r in %r', rule, raw)
            continue
        days_spec = match.group('days')
        times_spec = match.group('times')
        closed_flag = match.group('closed')
        try:
            weekdays = _expand_weekdays(days_spec)
        except ValueError as exc:
            logger.debug('opening_hours: %s in %r', exc, raw)
            continue
        if closed_flag or not times_spec:
            # Either explicit "off" or weekday-only without hours: treat as closed.
            continue
        for tr in times_spec.split(','):
            try:
                start, end = _parse_time_range(tr.strip())
            except ValueError as exc:
                logger.debug('opening_hours: %s in %r', exc, raw)
                continue
            overnight = end <= start and end != time(23, 59)
            for wd in weekdays:
                intervals.append(
                    OpeningInterval(weekday=wd, start=start, end=end, overnight=overnight)
                )

    if not intervals:
        return None
    return ParsedOpeningHours(intervals=tuple(intervals), source=raw)


def _point_in_interval(moment: time, interval: OpeningInterval, current_weekday: int) -> bool:
    """Check whether `moment` falls inside `interval` on `current_weekday`."""
    if interval.overnight:
        # The window started yesterday and extends past midnight.
        if interval.weekday == current_weekday and moment >= interval.start:
            return True
        prev_wd = (current_weekday - 1) % 7
        if interval.weekday == prev_wd and moment < interval.end:
            return True
        return False
    if interval.weekday != current_weekday:
        return False
    return interval.start <= moment < interval.end


class OpeningHoursTool:
    """High-level API for planning around opening hours.

    Typical usage from a planner/replanner::

        tool = OpeningHoursTool()
        status = tool.is_open_at(place.get('opening_hours'), dt)
        if status is False:
            # Skip the POI for this time slot.
            ...

    `is_open_at` returns:
        * ``True``  — POI is open at `dt`
        * ``False`` — POI is closed at `dt`
        * ``None``  — unknown / unparseable → caller decides (usually keep)
    """

    def is_open_at(
        self,
        opening_hours: Optional[str],
        dt: datetime,
    ) -> Optional[bool]:
        parsed = parse_opening_hours(opening_hours)
        if parsed is None:
            return None
        weekday = dt.weekday()
        moment = dt.time().replace(microsecond=0)
        for interval in parsed.intervals:
            if _point_in_interval(moment, interval, weekday):
                return True
        # At least one interval parsed but none matched → closed.
        return False

    def next_open_window(
        self,
        opening_hours: Optional[str],
        dt: datetime,
        horizon_days: int = 7,
    ) -> Optional[Tuple[datetime, datetime]]:
        """Return the next `(open_from, open_to)` datetime pair after `dt`.

        Scans up to `horizon_days` ahead. Returns `None` if nothing found or
        the tag is unparseable.
        """
        parsed = parse_opening_hours(opening_hours)
        if parsed is None:
            return None
        cursor_date = dt.date()
        for day_offset in range(horizon_days):
            current_date = cursor_date + timedelta(days=day_offset)
            wd = current_date.weekday()
            day_intervals = sorted(
                (iv for iv in parsed.intervals if iv.weekday == wd and not iv.overnight),
                key=lambda iv: iv.start,
            )
            for iv in day_intervals:
                open_from = datetime.combine(current_date, iv.start, tzinfo=dt.tzinfo)
                open_to = datetime.combine(current_date, iv.end, tzinfo=dt.tzinfo)
                if open_from >= dt or (open_from <= dt < open_to):
                    return (max(open_from, dt), open_to)
        return None

    def filter_places_by_time(
        self,
        places: Iterable[Dict[str, Any]],
        dt: datetime,
        *,
        keep_unknown: bool = True,
    ) -> List[Dict[str, Any]]:
        """Return a copy of `places` with closed POIs removed.

        Places without `opening_hours` are kept when `keep_unknown=True`
        (default) to avoid discarding 2GIS/Google POIs that simply lack the
        OSM tag.
        """
        kept: List[Dict[str, Any]] = []
        for place in places:
            status = self.is_open_at(place.get('opening_hours'), dt)
            if status is False:
                continue
            if status is None and not keep_unknown:
                continue
            kept.append(place)
        return kept
