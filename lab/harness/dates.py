# SPDX-License-Identifier: MIT
"""Date and time resolver for the assistant's tools. Pure code, standard library only.

Small models are unreliable at date arithmetic ("Friday" -> wrong date, "3 to 4pm" ->
16:00-17:00), so the tools accept the user's own words and resolve them HERE against a
"now" that the caller supplies as a timezone-aware datetime (zoneinfo). Nothing reads the
system clock, locale or TZ environment variable.

    parse_when("friday 3 to 4pm", now) -> When(date="2027-03-12", time="15:00", end_time="16:00", ...)

Policy: resolve what is unambiguous, and REJECT with a helpful message what is not
(WhenError), instead of guessing. The rules, all covered by tests/test_dates.py:

dates
  today, tonight, tomorrow, yesterday, day after tomorrow
  friday / this friday      the next Friday after today. Said ON a Friday: "this friday" is today,
                            bare "friday" is rejected (today or in a week?)
  next friday               the Friday of NEXT calendar week (weeks start Monday).
                            Rejected when today is that weekday.
  friday next week          the Friday of next calendar week, never rejected
  a week from friday        the next Friday after today, plus 7 days
  last friday               the most recent Friday before today (also what "friday" means in a
                            look-back filter such as "emails since friday": parse_when(..., past=True))
  the 20th                  this month, or next month if the 20th has passed; rejected if that
                            month has no such day ("the 31st" in a 30-day month)
  march 20, 20 march 2027   without a year: the next such date, today included
  3/20, 3/20/2027           month/day; rejected when day/month would also be valid and different
  2027-03-20                ISO
  end of the month, end of next month, end of the year, start of next month
  in 3 days, in two weeks, in a month, a week from today
  rejected: "next week", "this weekend", "end of the week", "soon", "later" (not one day)
times
  15:00, 3pm, 3:30 pm, noon, midnight (00:00, the START of the date)
  12:30pm = 12:30, 12:30am = 00:30; bare "12am"/"12pm" are rejected (say noon or midnight)
  a bare "3" is rejected (am or pm?); morning/afternoon/evening are rejected as clock times
  local times that do not exist (spring-forward gap) or occur twice (fall-back) are rejected
ranges
  3 to 4pm, 3-4pm, from 9am until 11:30am, 11 to 1pm (11:00-13:00), 14:00-15:30, 2pm for 45 minutes
  rejected: both ends without am/pm ("3 to 4"), end not after start or past midnight (10pm to 2am)
offsets
  in two hours, in 90 minutes, in half an hour, an hour from now: exact elapsed time from now
  (computed in UTC, so correct across daylight-saving changes); result has date AND time

Two later additions, off by default so that earlier measured configurations keep their behaviour
(the tool layer turns both on together; tests/test_dates_v3.py):

anchored=True   offsets from a date or time the caller already knows, so the model never subtracts:
  the day before 2027-04-02, 2 days after friday, a week before march 20, the night before april 2
  1 hour before 2:15pm (with the day in the same text or in the date field), 30 minutes after noon
  The anchor must itself be a date or time this module understands ("the day before departure"
  is rejected with a message that asks for the actual date).
overnight=True  ranges may run past midnight; the result then carries end_date (the next day):
  10pm to 2am, 9pm to 1, 11pm for 2 hours, 10pm to midnight, 10pm to 12am, 12am to 2am
  Inside a range "12am" is midnight and "12pm" is noon. A bare "12am"/"12pm" start is still
  rejected. A range longer than 16 hours is rejected as a probable am/pm slip.
"""
import calendar
import re
from dataclasses import dataclass, field
from datetime import date as _date, datetime, timedelta, timezone

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December"]
_WD = {}
for _i, _n in enumerate(WEEKDAYS):
    _WD[_n.lower()] = _i
    _WD[_n[:3].lower()] = _i
_WD.update({"tues": 1, "thur": 3, "thurs": 3, "weds": 2})
_MO = {}
for _i, _n in enumerate(MONTHS):
    _MO[_n.lower()] = _i + 1
    _MO[_n[:3].lower()] = _i + 1
_MO["sept"] = 9
_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
        "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30,
        "forty-five": 45, "forty five": 45, "sixty": 60, "ninety": 90, "couple": 2, "a couple": 2, "a couple of": 2,
        "couple of": 2}
_WD_ALT = "|".join(sorted(_WD, key=len, reverse=True))
_MO_ALT = "|".join(sorted(_MO, key=len, reverse=True))
_NUM_ALT = "|".join(sorted((re.escape(k) for k in _NUM), key=len, reverse=True))
_PARTS_OF_DAY = ("morning", "afternoon", "evening", "night")


class WhenError(ValueError):
    """An expression that cannot be resolved safely. `code` is stable; str() is for the model/user."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass
class When:
    date: str = None          # YYYY-MM-DD
    time: str = None          # HH:MM, 24-hour
    end_time: str = None      # HH:MM, 24-hour
    end_date: str = None      # YYYY-MM-DD, set only when the range ends on a later day than `date`
    notes: list = field(default_factory=list)

    @property
    def weekday(self):
        return WEEKDAYS[_date.fromisoformat(self.date).weekday()] if self.date else None


def human_date(iso):
    d = _date.fromisoformat(iso)
    return f"{WEEKDAYS[d.weekday()]}, {MONTHS[d.month - 1]} {d.day}, {d.year}"


def _require_aware(now):
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise TypeError("now must be a timezone-aware datetime")


def _clean(text):
    if not isinstance(text, str):
        raise WhenError("not_text", f"expected text, got {type(text).__name__}")
    t = text.strip().lower()
    t = t.replace("\u2013", "-").replace("\u2014", "-").replace("\u2019", "'")
    t = re.sub(r"\ba\.m\.?", "am", t)
    t = re.sub(r"\bp\.m\.?", "pm", t)
    t = t.replace(",", " ")
    t = re.sub(r"\s+", " ", t).strip(" .")
    return t


def _num(tok):
    tok = tok.strip()
    if tok.isdigit():
        return int(tok)
    if tok in _NUM:
        return _NUM[tok]
    raise WhenError("unknown_number", f"cannot read '{tok}' as a number")


# ------------------------------------------------------------------ times
_T = r"(?:\d{1,2}(?::\d{2})?\s?(?:(?:am|pm)\b)?|\bnoon\b|\bmidday\b|\bmidnight\b)"
_T_STRICT = r"(?:\d{1,2}:\d{2}\s?(?:(?:am|pm)\b)?|\d{1,2}\s?(?:am|pm)\b|\bnoon\b|\bmidday\b|\bmidnight\b)"
_RANGE_RE = re.compile(rf"(?:\bfrom\s+)?(?<![\d:/-])({_T})\s?(?:-|to|until|till|through)\s?({_T})(?![\d:/-])")
_DUR_RE = re.compile(rf"(?<![\d:/-])({_T_STRICT})\s+for\s+((?:\d+|{_NUM_ALT})(?:\s+and\s+a\s+half)?|half\s+an?)\s*(minutes?|mins?|hours?|hrs?)(\s+and\s+a\s+half)?")
_SINGLE_RE = re.compile(rf"(?:\bat\s+|@\s?)?(?<![\d:/-])({_T_STRICT})(?![\d:/-])")


def _one_time(tok, meridiem_hint=None, allow12=False):
    """-> (minutes since midnight, had_meridiem, was_24h). A bare number needs meridiem_hint.
    allow12: read "12am" as midnight and "12pm" as noon instead of rejecting them (range boundaries)."""
    tok = tok.strip()
    if tok in ("noon", "midday"):
        return 12 * 60, True, False
    if tok == "midnight":
        return 0, True, False
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s?(am|pm)?", tok)
    if not m:
        raise WhenError("bad_time", f"'{tok}' is not a time. Use 3pm, 3:30pm or 15:30.")
    h, mi, mer = int(m.group(1)), int(m.group(2) or 0), m.group(3)
    if mi > 59:
        raise WhenError("bad_time", f"'{tok}' is not a valid time (minutes above 59).")
    if mer:
        if not 1 <= h <= 12:
            raise WhenError("bad_time", f"'{tok}' is not a valid time: with am/pm the hour must be 1 to 12.")
        if h == 12 and mi == 0 and not allow12:
            raise WhenError("ambiguous_12", f"'{tok}' is ambiguous. Say 'noon' or 'midnight', or use 12:00 / 00:00.")
        return ((h % 12) + (12 if mer == "pm" else 0)) * 60 + mi, True, False
    if meridiem_hint and 1 <= h <= 12 and not m.group(1).startswith("0"):
        return ((h % 12) + (12 if meridiem_hint == "pm" else 0)) * 60 + mi, False, False
    if m.group(2) is not None or h > 12:
        if h > 23:
            raise WhenError("bad_time", f"'{tok}' is not a valid time (hours run 00 to 23).")
        return h * 60 + mi, False, True
    raise WhenError("ambiguous_ampm", f"'{tok}' could be {tok}am or {tok}pm. Say which, or use 24-hour time like 15:00.")


def _meridiem(tok):
    m = re.search(r"(am|pm)$", tok.strip())
    if m:
        return m.group(1)
    return {"noon": "pm", "midday": "pm", "midnight": "am"}.get(tok.strip())


def _is_bare(tok):
    return bool(re.fullmatch(r"\d{1,2}", tok.strip())) and int(tok) <= 12


def _is_open(tok):
    """1..12 with no am/pm and no leading zero ("3", "2:30"): could be either half of the day."""
    m = re.fullmatch(r"(\d{1,2})(?::\d{2})?", tok.strip())
    return bool(m) and 1 <= int(m.group(1)) <= 12 and not m.group(1).startswith("0")


MAX_OVERNIGHT_MIN = 16 * 60


def _range(a, b, overnight=False):
    """Two time tokens -> (start_minutes, end_minutes). With overnight=True the end may be past
    24:00 (1440 or more): the range then finishes on the next day."""
    if overnight:
        return _range_overnight(a, b)
    ma, mb = _meridiem(a), _meridiem(b)
    oa, ob = _is_open(a), _is_open(b)
    if oa and ob and (_is_bare(a) or _is_bare(b)):
        raise WhenError("ambiguous_ampm", f"'{a} to {b}' has no am/pm. Say e.g. '{a} to {b}pm' or use 24-hour times.")
    if oa and mb is not None:
        end = _one_time(b)[0]
        start = _one_time(a, mb)[0]
        if start >= end:  # "11 to 1pm" means 11am
            other = _one_time(a, "am" if mb == "pm" else "pm")[0]
            if other < end:
                start = other
    elif ob and ma is not None:
        start = _one_time(a)[0]
        end = _one_time(b, ma)[0]
        if end <= start and ma == "am":  # "11am to 1" means 1pm
            end = _one_time(b, "pm")[0]
    elif (_is_bare(a) and not ob) or (_is_bare(b) and not oa):
        raise WhenError("ambiguous_ampm", f"'{a} to {b}' mixes a bare hour with 24-hour time. Add am/pm or use HH:MM for both.")
    else:
        start, end = _one_time(a)[0], _one_time(b)[0]
    if end == start:
        raise WhenError("empty_range", f"'{a} to {b}' starts and ends at the same time.")
    if end < start:
        raise WhenError("crosses_midnight", f"'{a} to {b}' would end on the next day. Give an end time on the same day, "
                                            "or create two events.")
    return start, end


def _range_overnight(a, b):
    def one(tok, hint=None):
        return _one_time(tok, hint, allow12=True)[0]
    ma, mb = _meridiem(a), _meridiem(b)
    oa, ob = _is_open(a), _is_open(b)
    if oa and ob and (_is_bare(a) or _is_bare(b)):
        raise WhenError("ambiguous_ampm", f"'{a} to {b}' has no am/pm. Say e.g. '{a} to {b}pm' or use 24-hour times.")
    if oa and mb is not None:
        end = one(b)
        start = one(a, mb)
        if start >= end:  # "11 to 1pm" means 11am; "10 to 2am" means 10pm
            other = one(a, "am" if mb == "pm" else "pm")
            if other < end or mb == "am":
                start = other
    elif ob and ma is not None:
        start = one(a)
        end = one(b, ma)
        if end <= start:  # "11am to 1" means 1pm; "9pm to 1" means 1am the next day
            end = one(b, "pm" if ma == "am" else "am")
    elif (_is_bare(a) and not ob) or (_is_bare(b) and not oa):
        raise WhenError("ambiguous_ampm", f"'{a} to {b}' mixes a bare hour with 24-hour time. Add am/pm or use HH:MM for both.")
    else:
        start, end = one(a), one(b)
    if end == start:
        raise WhenError("empty_range", f"'{a} to {b}' starts and ends at the same time.")
    if end < start:
        end += 24 * 60
    if end - start > MAX_OVERNIGHT_MIN:
        raise WhenError("too_long", f"'{a} to {b}' would last {(end - start) // 60} hours and end on the next day. "
                                    "Check am/pm with the user.")
    return start, end


def _fmt(minutes):
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def _extract_time(t, overnight=False):
    """Find a time or range inside cleaned text. -> (start, end, rest, shift): HH:MM strings or None,
    and the number of days after the start day on which the range ends (0, or 1 with overnight=True)."""
    m = _DUR_RE.search(t)
    if m:
        start = _one_time(m.group(1))[0]
        qty = m.group(2).strip()
        unit = m.group(3)
        half = bool(m.group(4)) or " and a half" in qty
        qty = qty.replace(" and a half", "").strip()
        n = 0.5 if qty.startswith("half") else _num(qty)
        if half:
            n += 0.5
        mins = int(round(n * (60 if unit.startswith("h") else 1)))
        if mins <= 0:
            raise WhenError("empty_range", "the duration must be longer than zero.")
        end = start + mins
        if end >= 24 * 60 and not overnight:
            raise WhenError("crosses_midnight", "that would end on the next day. Give an end time on the same day.")
        if mins > MAX_OVERNIGHT_MIN and end > 24 * 60:
            raise WhenError("too_long", "that would last more than 16 hours and end on a later day. Check the duration with the user.")
        return _fmt(start), _fmt(end), (t[:m.start()] + " " + t[m.end():]).strip(), end // (24 * 60)
    m = _RANGE_RE.search(t)
    if m and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", t):
        a, b = m.group(1), m.group(2)
        # "march 3 - 5" style is not supported as a time range: need a time marker on one side
        if _is_bare(a) and _is_bare(b):
            if re.fullmatch(rf"(?:from\s+)?{_T}\s?(?:-|to|until|till|through)\s?{_T}", t):
                _range(a, b)  # raises ambiguous_ampm
        else:
            s, e = _range(a, b, overnight)
            return _fmt(s), _fmt(e), (t[:m.start()] + " " + t[m.end():]).strip(), e // (24 * 60)
    m = _SINGLE_RE.search(t)
    if m:
        s = _one_time(m.group(1))[0]
        return _fmt(s), None, (t[:m.start()] + " " + t[m.end():]).strip(), 0
    return None, None, t, 0


def parse_time(text, overnight=False, allow12=False, full=False):
    """A clock time or a range, nothing else. -> (start 'HH:MM', end 'HH:MM' or None), or with
    full=True (start, end, shift) where shift is how many days after the start day the range ends.
    allow12: a lone "12am"/"12pm" is read as midnight/noon (used for an end-time field)."""
    t = _clean(text)
    if not t:
        raise WhenError("empty", "the time is empty.")
    t = re.sub(r"^(at|around|about)\s+", "", t)
    for p in _PARTS_OF_DAY:
        if t in (p, "in the " + p, "this " + p, "at " + p):
            raise WhenError("vague_time", f"'{text}' is not a clock time. Ask the user for a time such as 9am.")
    if re.fullmatch(r"\d{1,2}", t):
        _one_time(t)  # raises ambiguous_ampm or returns for 13..23
    if allow12 and re.fullmatch(r"12(:00)?\s?(am|pm)", t):
        one = "00:00" if t.endswith("am") else "12:00"
        return (one, None, 0) if full else (one, None)
    start, end, rest, shift = _extract_time(t, overnight)
    rest = re.sub(r"\b(at|from)\b", "", rest).strip()
    if start is None:
        if re.fullmatch(r"\d{1,2}", t) and int(t) > 12:
            one = _fmt(_one_time(t)[0])
            return (one, None, 0) if full else (one, None)
        raise WhenError("bad_time", f"'{text}' is not a time. Use 3pm, 3:30pm, 15:30, or a range like '3 to 4pm'.")
    if rest:
        raise WhenError("bad_time", f"could not read '{rest}' in the time '{text}'. Put the day in the date field.")
    return (start, end, shift) if full else (start, end)


# ------------------------------------------------------------------ dates
def _add_months(d, n):
    y, m = divmod(d.year * 12 + (d.month - 1) + n, 12)
    return y, m + 1


def _mk(y, m, d, what):
    try:
        return _date(y, m, d)
    except ValueError:
        last = calendar.monthrange(y, m)[1] if 1 <= m <= 12 else None
        if last:
            raise WhenError("no_such_date", f"{what}: {MONTHS[m - 1]} {y} has only {last} days.")
        raise WhenError("no_such_date", f"{what}: there is no such date.")


def _parse_date(t, today, notes, past=False):
    """Cleaned, non-empty text -> date. Raises WhenError. past=True: the text is a look-back ("since monday")."""
    t = re.sub(r"^since\s+", "", t) if past else t
    t = re.sub(r"^(on|by|for|due|until|before)\s+", "", t).strip()
    t = re.sub(r"\s+", " ", t)
    if t in ("today", "tonight", "now", "this evening", "this afternoon", "this morning", "end of the day", "end of day", "eod"):
        return today
    if t in ("tomorrow", "tmrw", "tmr"):
        return today + timedelta(days=1)
    if t == "yesterday":
        return today - timedelta(days=1)
    if t in ("day after tomorrow", "the day after tomorrow", "overmorrow"):
        return today + timedelta(days=2)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
    if m:
        return _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)), f"'{t}'")
    # relative day/week/month/year offsets
    m = re.fullmatch(rf"(?:in\s+)?(\d+|{_NUM_ALT})\s+(day|week|month|year)s?(?:\s+from\s+(?:now|today))?", t)
    if m and (t.startswith("in ") or " from " in t):
        n, unit = _num(m.group(1)), m.group(2)
        if unit == "day":
            return today + timedelta(days=n)
        if unit == "week":
            return today + timedelta(days=7 * n)
        y, mo = _add_months(today, n if unit == "month" else 12 * n)
        return _mk(y, mo, today.day, f"'{t}' from {today.isoformat()}")
    m = re.fullmatch(rf"(?:a|one|1)\s+week\s+from\s+(today|tomorrow|{_WD_ALT})", t)
    if m:
        base = m.group(1)
        if base == "today":
            return today + timedelta(days=7)
        if base == "tomorrow":
            return today + timedelta(days=8)
        delta = (_WD[base] - today.weekday()) % 7 or 7
        return today + timedelta(days=delta + 7)
    # weekdays
    monday_next = today + timedelta(days=7 - today.weekday())
    m = re.fullmatch(rf"({_WD_ALT})\s+(?:of\s+)?next\s+week|next\s+week(?:\s+on)?\s+({_WD_ALT})", t)
    if m:
        return monday_next + timedelta(days=_WD[m.group(1) or m.group(2)])
    m = re.fullmatch(rf"(this\s+coming|this|coming|next|last|on)?\s*({_WD_ALT})", t)
    if m:
        mod, w = (m.group(1) or "").split()[0] if m.group(1) else "", _WD[m.group(2)]
        name = WEEKDAYS[w]
        delta = (w - today.weekday()) % 7
        if mod == "last" or (past and mod in ("", "on")):
            return today - timedelta(days=(today.weekday() - w) % 7 or 7)
        if mod == "next":
            if delta == 0:
                raise WhenError("ambiguous_weekday", f"today is {name}, so 'next {name.lower()}' is ambiguous. "
                                                     f"Say 'today' or '{name.lower()} next week'.")
            d = monday_next + timedelta(days=w)
            notes.append(f"'next {name.lower()}' read as the {name} of next week; plain '{name.lower()}' would be "
                         f"{(today + timedelta(days=delta)).isoformat()}")
            return d
        if delta == 0:
            if mod == "this":
                return today
            raise WhenError("ambiguous_weekday", f"today is {name}. Say 'today' or '{name.lower()} next week'.")
        return today + timedelta(days=delta)
    # month boundaries
    m = re.fullmatch(r"(?:the\s+)?(end|start|beginning|first day|last day)\s+of\s+(?:(the|this|next)\s+)?(month|year|week|day)|month end|eom", t)
    if m:
        edge, which, unit = (m.group(1) or "end"), (m.group(2) or "the"), (m.group(3) or "month")
        end = edge in ("end", "last day")
        if unit == "week":
            raise WhenError("ambiguous_range", f"'{t}' is ambiguous (Friday or Sunday?). Name the day.")
        if unit == "day":
            return today
        if unit == "year":
            y = today.year + (1 if which == "next" else 0)
            return _date(y, 12, 31) if end else _date(y, 1, 1)
        y, mo = _add_months(today, 1 if which == "next" else 0)
        return _date(y, mo, calendar.monthrange(y, mo)[1]) if end else _date(y, mo, 1)
    # month name + day
    m = re.fullmatch(rf"({_MO_ALT})\.?\s+(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?(?:\s+(\d{{4}}))?", t) or \
        re.fullmatch(rf"(?:the\s+)?(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MO_ALT})\.?(?:\s+(\d{{4}}))?", t)
    if m:
        g = m.groups()
        mo, day = (_MO[g[0]], int(g[1])) if g[0] in _MO else (_MO[g[1]], int(g[0]))
        if g[2]:
            return _mk(int(g[2]), mo, day, f"'{t}'")
        if mo == 2 and day == 29:
            for y in range(today.year, today.year + 9):
                if calendar.isleap(y) and _date(y, 2, 29) >= today:
                    if y != today.year:
                        raise WhenError("no_such_date", f"'{t}': {today.year} is not a leap year; the next February 29 is in {y}. Give the year.")
                    return _date(y, 2, 29)
        d = _mk(today.year, mo, day, f"'{t}'")
        if past:
            return d if d <= today else _mk(today.year - 1, mo, day, f"'{t}'")
        if d < today:
            d = _mk(today.year + 1, mo, day, f"'{t}'")
            notes.append(f"{MONTHS[mo - 1]} {day} has passed this year, so {d.year} was used")
        return d
    # bare day of month
    m = re.fullmatch(r"(?:the\s+)?(\d{1,2})(st|nd|rd|th)(?:\s+of\s+(?:the|this)\s+month)?", t)
    if m:
        day = int(m.group(1))
        if day < 1:
            raise WhenError("no_such_date", f"'{t}' is not a day of the month.")
        last = calendar.monthrange(today.year, today.month)[1]
        if past:
            if day <= today.day:
                return _date(today.year, today.month, day)
            y, mo = _add_months(today, -1)
            return _mk(y, mo, day, f"'{t}'")
        if day >= today.day:
            if day > last:
                raise WhenError("no_such_date", f"'{t}': {MONTHS[today.month - 1]} has only {last} days. Name the month.")
            return _date(today.year, today.month, day)
        y, mo = _add_months(today, 1)
        d = _mk(y, mo, day, f"'{t}' (the {day}th has passed this month)")
        notes.append(f"the {day}{m.group(2)} has passed this month, so {MONTHS[mo - 1]} was used")
        return d
    # numeric m/d[/y]
    m = re.fullmatch(r"(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2}|\d{4}))?", t)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if a <= 12 and b <= 12 and a != b:
            raise WhenError("ambiguous_numeric_date", f"'{t}' could be month/day or day/month. Write the month name or use YYYY-MM-DD.")
        mo, day = (a, b) if a <= 12 else (b, a)
        if y:
            return _mk(int(y) + (2000 if len(y) == 2 else 0), mo, day, f"'{t}'")
        d = _mk(today.year, mo, day, f"'{t}'")
        if d < today:
            d = _mk(today.year + 1, mo, day, f"'{t}'")
            notes.append(f"that date has passed this year, so {d.year} was used")
        return d
    if re.fullmatch(r"(this|next|the|over the|the coming)?\s*(week|weekend|month|year)", t):
        raise WhenError("ambiguous_range", f"'{t}' is not a single day. Ask the user which day.")
    if t in ("soon", "later", "sometime", "asap", "someday", "eventually"):
        raise WhenError("vague_date", f"'{t}' is not a date. Ask the user which day.")
    raise WhenError("unknown_date", f"could not understand the date '{t}'. Use words like 'tomorrow', 'friday', "
                                    "'next tuesday', 'march 20', 'in 3 days', or YYYY-MM-DD.")


def _check_local(d, hhmm, tz, what):
    """Reject wall-clock times that do not exist or happen twice on that date in tz."""
    h, mi = int(hhmm[:2]), int(hhmm[3:])
    naive = datetime(d.year, d.month, d.day, h, mi)
    a = naive.replace(tzinfo=tz, fold=0)
    b = naive.replace(tzinfo=tz, fold=1)
    if a.utcoffset() == b.utcoffset():
        return
    back = a.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)
    if back != naive:
        raise WhenError("nonexistent_local_time", f"{hhmm} on {d.isoformat()} does not exist in {tz.key}: clocks jump forward "
                                                  f"that night ({what}). Pick another time.")
    raise WhenError("ambiguous_local_time", f"{hhmm} on {d.isoformat()} happens twice in {tz.key}: clocks go back that night "
                                            f"({what}). Pick a time outside that hour.")


_OFFSET_RE = re.compile(
    rf"(?:in\s+)?(?:(half\s+an?)\s+(hour)|(\d+|{_NUM_ALT})\s+(minute|min|hour|hr)s?(\s+and\s+a\s+half)?"
    rf"(?:\s+and\s+(\d+|{_NUM_ALT})\s+(minute|min)s?)?)(?:\s+from\s+now)?")


_BEFORE_AFTER = r"(before|after|prior to|ahead of|following)"
_ANCHOR_DATE_RE = re.compile(
    rf"(?:(the)|(\d+|{_NUM_ALT}))\s+(day|week|month|night|evening)s?\s+{_BEFORE_AFTER}\s+(?:on\s+)?(.+)")
_ANCHOR_TIME_RE = re.compile(
    rf"(?:(half\s+an?)\s+hour|(\d+|{_NUM_ALT})\s+(minute|min|hour|hr)s?(\s+and\s+a\s+half)?)\s+{_BEFORE_AFTER}\b(?:\s+(?:on|at)\b)?")


def _anchor_minutes(m):
    """Signed minutes for an _ANCHOR_TIME_RE match."""
    if m.group(1):
        mins = 30
    else:
        n, unit = _num(m.group(2)), m.group(3)
        mins = n * 60 if unit.startswith("h") else n
        if m.group(4):
            mins += 30 if unit.startswith("h") else 0
    return mins if m.group(5) in ("after", "following") else -mins


def _anchored_date(rest, today, notes, past):
    """'the day before 2027-04-02' / '2 days after friday' -> date, or None when `rest` is not such a phrase."""
    m = _ANCHOR_DATE_RE.fullmatch(rest)
    if not m:
        return None
    n = 1 if m.group(1) else _num(m.group(2))
    unit, sign, anchor = m.group(3), (1 if m.group(4) in ("after", "following") else -1), m.group(5).strip()
    try:
        base = _parse_date(anchor, today, notes, past)
    except WhenError as e:
        if e.code == "unknown_date":
            raise WhenError("unknown_anchor", f"'{anchor}' is not a date this tool knows. Find the actual date first and pass it, "
                                              f"for example '{rest[:m.start(5)].strip()} 2027-04-02'.")
        raise
    if unit == "month":
        y, mo = _add_months(base, sign * n)
        d = _mk(y, mo, base.day, f"'{rest}'")
    else:
        d = base + timedelta(days=sign * n * (7 if unit == "week" else 1))
    notes.append(f"{n} {unit if unit not in ('night', 'evening') else 'day'}{'s' if n != 1 else ''} "
                 f"{'after' if sign > 0 else 'before'} {base.isoformat()} ({WEEKDAYS[base.weekday()]})")
    return d


def parse_when(text, now, time_text=None, end_text=None, past=False, anchored=False, overnight=False):
    """Resolve a natural or ISO date/time expression against `now` (timezone-aware).

    text       the date field as the model passed it; may also contain a time or range
               ("tomorrow 3pm", "friday 3 to 4pm", "in two hours", "2027-03-12T15:00")
    time_text  optional separate time field ("3pm", "15:00", "3 to 4pm")
    end_text   optional separate end-time field
    past       the expression is a look-back filter ("since monday"): a bare weekday, month-day or
               day-of-month means the most recent one before today instead of the next one
    anchored   also accept offsets from a known date or time ("the day before 2027-04-02",
               "1 hour before 2:15pm"); see the module docstring
    overnight  also accept ranges that run past midnight; the result then has end_date
    Returns When(date, time, end_time, end_date, notes). Raises WhenError with a helpful message.
    """
    _require_aware(now)
    tz = now.tzinfo
    today = now.date()
    w = When()
    t = _clean(text if text is not None else "")
    if not t:
        raise WhenError("empty", "the date is empty. Ask the user which day.")
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[t ](\d{1,2}:\d{2})(?::\d{2})?", t)
    if m:
        t = f"{m.group(1)} at {m.group(2)}"
    # exact elapsed-time offsets: "in two hours", "an hour from now", "in 90 minutes"
    m = _OFFSET_RE.fullmatch(t)
    if m and (t.startswith("in ") or t.endswith(" from now")):
        if m.group(1):
            mins = 30
        else:
            n, unit = _num(m.group(3)), m.group(4)
            mins = n * 60 if unit.startswith("h") else n
            if m.group(5):
                mins += 30 if unit.startswith("h") else 0
            if m.group(6):
                mins += _num(m.group(6))
        if time_text or end_text:
            raise WhenError("conflict", f"'{text}' already fixes the time; leave the time field out.")
        target = (now.astimezone(timezone.utc) + timedelta(minutes=mins)).astimezone(tz)
        w.date, w.time = target.date().isoformat(), f"{target.hour:02d}:{target.minute:02d}"
        w.notes.append(f"{mins} minutes after now ({now.strftime('%Y-%m-%d %H:%M')} {tz.key})")
        return w
    start, end, rest, shift = _extract_time(t, overnight)
    rest = re.sub(r"\b(at|from)\b\s*$", "", rest).strip()
    rest = re.sub(r"^(at|from)\b", "", rest).strip()
    rest = re.sub(r"\s+", " ", rest)
    delta = None  # minutes to add to the anchor time ("1 hour before 2:15pm")
    if anchored:
        m = _ANCHOR_TIME_RE.search(rest)
        if m:
            if start is None or end is not None:
                raise WhenError("unknown_anchor", f"'{text}' needs one clock time to count from, for example '1 hour before 2:15pm'.")
            delta = _anchor_minutes(m)
            rest = re.sub(r"\s+", " ", (rest[:m.start()] + " " + rest[m.end():])).strip()
            rest = re.sub(r"^(on|at)\s+", "", rest)
    vague = None
    is_anchor = anchored and bool(_ANCHOR_DATE_RE.fullmatch(rest))  # "the night before april 2": keep the phrase whole
    for p in _PARTS_OF_DAY:
        m2 = None if is_anchor else re.search(rf"\b(in the |this |at )?{p}\b", rest)
        if m2 and rest not in ("tonight", "this evening", "this afternoon", "this morning"):
            vague = p
            rest = (rest[:m2.start()] + rest[m2.end():]).strip()
    if rest in ("this evening", "this afternoon", "this morning", "tonight"):
        vague = rest.split()[-1]
    if not rest:
        if start is None:
            raise WhenError("unknown_date", f"could not understand the date '{text}'.")
        raise WhenError("missing_date", f"'{text}' has a time but no day. Ask the user which day.")
    d = (_anchored_date(rest, today, w.notes, past) if anchored else None) or _parse_date(rest, today, w.notes, past)
    if time_text is not None and str(time_text).strip():
        tt = _clean(str(time_text))
        m = _ANCHOR_TIME_RE.search(tt) if anchored else None
        if m:
            if delta is not None:
                raise WhenError("conflict", "two offsets were given. Send one of them.")
            delta = _anchor_minutes(m)
            tt = re.sub(r"\s+", " ", (tt[:m.start()] + " " + tt[m.end():])).strip()
            if not tt:
                raise WhenError("unknown_anchor", f"'{time_text}' needs a clock time to count from, for example '1 hour before 2:15pm'.")
        s2, e2, sh2 = parse_time(tt, overnight, full=True)
        if m and e2:
            raise WhenError("unknown_anchor", f"'{time_text}' needs one clock time to count from, not a range.")
        if start is not None and start != s2:
            raise WhenError("conflict", f"the date field says {start} but the time field says {s2}. Send one of them.")
        start = s2
        if e2:
            end, shift = e2, sh2
    if end_text is not None and str(end_text).strip():
        e3, extra = parse_time(end_text, allow12=overnight)
        if extra:
            raise WhenError("bad_time", f"the end time '{end_text}' must be a single time.")
        if end is not None and end != e3:
            raise WhenError("conflict", f"two different end times were given ({end} and {e3}).")
        if end is None:
            shift = 0
        end = e3
    if delta is not None:
        if start is None:
            raise WhenError("unknown_anchor", f"'{text}' needs a clock time to count from, for example '1 hour before 2:15pm'.")
        if end is not None:
            raise WhenError("unknown_anchor", "an offset from a time cannot be combined with an end time.")
        anchor = datetime(d.year, d.month, d.day, int(start[:2]), int(start[3:]))
        target = anchor + timedelta(minutes=delta)
        w.notes.append(f"{abs(delta)} minutes {'after' if delta > 0 else 'before'} {start} on {d.isoformat()}")
        d, start = target.date(), f"{target.hour:02d}:{target.minute:02d}"
    if end is not None:
        if start is None:
            raise WhenError("missing_time", "an end time was given without a start time.")
        if end == start and not shift:
            raise WhenError("empty_range", "the event starts and ends at the same time.")
        if end <= start and not shift:
            if not overnight:
                raise WhenError("crosses_midnight", f"{start} to {end} would end on the next day. Give an end time on the same day.")
            shift = 1
            mins = 24 * 60 - (int(start[:2]) * 60 + int(start[3:])) + int(end[:2]) * 60 + int(end[3:])
            if mins > MAX_OVERNIGHT_MIN:
                raise WhenError("too_long", f"{start} to {end} would last {mins // 60} hours and end on the next day. Check am/pm with the user.")
    if vague and start is None:
        w.notes.append(f"'{vague}' is not a clock time, so no time was set")
    w.date, w.time, w.end_time = d.isoformat(), start, end
    if start:
        _check_local(d, start, tz, "start time")
    if end:
        d_end = d + timedelta(days=shift)
        if shift:
            w.end_date = d_end.isoformat()
            w.notes.append(f"ends the next day, {WEEKDAYS[d_end.weekday()]} {w.end_date}, at {end}")
        _check_local(d_end, end, tz, "end time")
    return w


def is_iso_date(s):
    return isinstance(s, str) and bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", s.strip()))
