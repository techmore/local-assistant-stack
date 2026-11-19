# SPDX-License-Identifier: MIT
"""Resolver tests. Pure code: no model, no clock, no locale, no OS-specific behaviour."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import _path  # noqa: F401
from dates import WhenError, human_date, parse_time, parse_when

CHI = ZoneInfo("America/Chicago")
THU = datetime(2027, 3, 11, 16, 40, tzinfo=CHI)      # Thursday; DST starts Sunday 2027-03-14
WED = datetime(2026, 11, 18, 10, 15, tzinfo=ZoneInfo("America/Los_Angeles"))


def at(y, mo, d, h=12, mi=0, tz=CHI):
    return datetime(y, mo, d, h, mi, tzinfo=tz)


class Base(unittest.TestCase):
    def ok(self, expr, now, date=None, time=None, end=None, **kw):
        w = parse_when(expr, now, **kw)
        self.assertEqual((w.date, w.time, w.end_time), (date, time, end), expr)
        return w

    def bad(self, expr, now, code, **kw):
        with self.assertRaises(WhenError, msg=expr) as cm:
            parse_when(expr, now, **kw)
        self.assertEqual(cm.exception.code, code, f"{expr!r}: {cm.exception}")
        self.assertTrue(str(cm.exception))


class Weekdays(Base):
    def test_bare_weekday_is_next_occurrence(self):
        for expr, d in [("friday", "2027-03-12"), ("Fri", "2027-03-12"), ("on Friday", "2027-03-12"), ("saturday", "2027-03-13"),
                        ("sunday", "2027-03-14"), ("monday", "2027-03-15"), ("tues", "2027-03-16"), ("wednesday", "2027-03-17"),
                        ("this friday", "2027-03-12"), ("this coming monday", "2027-03-15")]:
            self.ok(expr, THU, d)

    def test_same_weekday_today(self):
        self.bad("thursday", THU, "ambiguous_weekday")
        self.bad("next thursday", THU, "ambiguous_weekday")
        self.ok("this thursday", THU, "2027-03-11")
        self.ok("thursday next week", THU, "2027-03-18")

    def test_next_friday_on_a_friday_is_rejected(self):
        fri = at(2027, 3, 12)
        self.bad("next friday", fri, "ambiguous_weekday")
        self.bad("friday", fri, "ambiguous_weekday")
        self.ok("friday next week", fri, "2027-03-19")

    def test_next_weekday_is_next_calendar_week(self):
        self.ok("next tuesday", THU, "2027-03-16")
        w = self.ok("next friday", THU, "2027-03-19")
        self.assertIn("2027-03-12", w.notes[0])          # says what plain "friday" would have been
        self.ok("next monday", at(2027, 3, 14), "2027-03-15")   # Sunday -> tomorrow
        self.ok("next sunday", at(2027, 3, 13), "2027-03-21")   # Saturday -> Sunday of next week
        self.ok("next week on wednesday", THU, "2027-03-17")

    def test_week_from_and_last(self):
        self.ok("a week from friday", THU, "2027-03-19")
        self.ok("a week from today", THU, "2027-03-18")
        self.ok("last friday", THU, "2027-03-05")
        self.ok("last thursday", THU, "2027-03-04")

    def test_rollover_across_month_and_year(self):
        self.ok("friday", at(2027, 3, 30), "2027-04-02")            # Tuesday -> next month
        self.ok("monday", at(2026, 12, 30), "2027-01-04")           # Wednesday -> next year
        self.ok("next tuesday", at(2026, 12, 31), "2027-01-05")
        self.ok("tomorrow", at(2026, 12, 31), "2027-01-01")
        self.ok("tomorrow", at(2028, 2, 28), "2028-02-29")          # leap year
        self.ok("tomorrow", at(2027, 2, 28), "2027-03-01")
        self.ok("day after tomorrow", at(2027, 4, 29), "2027-05-01")

    def test_every_weekday_from_every_start_day(self):
        import datetime as dt
        names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        for offset in range(7):
            now = at(2027, 3, 8) + dt.timedelta(days=offset)
            for i, n in enumerate(names):
                if i == now.weekday():
                    continue
                d = dt.date.fromisoformat(parse_when(n, now).date)
                self.assertEqual(d.weekday(), i)
                self.assertTrue(0 < (d - now.date()).days < 7)
                nx = dt.date.fromisoformat(parse_when("next " + n, now).date)
                self.assertEqual(nx.weekday(), i)
                self.assertEqual(nx.isocalendar()[:2], (now.date() + dt.timedelta(days=7)).isocalendar()[:2])


class LookBack(Base):
    def test_past_preference(self):
        for expr, d in [("monday", "2027-03-08"), ("since monday", "2027-03-08"), ("thursday", "2027-03-04"), ("friday", "2027-03-05"),
                        ("yesterday", "2027-03-10"), ("today", "2027-03-11"), ("march 1", "2027-03-01"), ("march 20", "2026-03-20"),
                        ("the 5th", "2027-03-05"), ("the 20th", "2027-02-20"), ("2027-01-02", "2027-01-02"), ("last friday", "2027-03-05")]:
            self.ok(expr, THU, d, past=True)
        self.bad("the 30th", THU, "no_such_date", past=True)        # February has no 30th
        self.ok("monday", at(2027, 1, 2), "2026-12-28", past=True)  # across the year boundary


class CalendarDates(Base):
    def test_relative_words(self):
        self.ok("today", THU, "2027-03-11")
        self.ok("Tomorrow", THU, "2027-03-12")
        self.ok("yesterday", THU, "2027-03-10")
        self.ok("the day after tomorrow", THU, "2027-03-13")
        self.ok("in 3 days", THU, "2027-03-14")
        self.ok("in two weeks", THU, "2027-03-25")
        self.ok("3 days from now", THU, "2027-03-14")
        self.ok("in a month", THU, "2027-04-11")
        self.ok("in a year", THU, "2028-03-11")

    def test_month_arithmetic_rejects_missing_days(self):
        self.bad("in a month", at(2027, 1, 31), "no_such_date")
        self.ok("in a month", at(2027, 1, 28), "2027-02-28")
        self.bad("in a year", at(2028, 2, 29), "no_such_date")

    def test_iso(self):
        self.ok("2027-03-20", THU, "2027-03-20")
        self.ok("2027-03-12T15:00", THU, "2027-03-12", "15:00")
        self.ok("2027-03-12 09:05", THU, "2027-03-12", "09:05")
        self.bad("2027-02-30", THU, "no_such_date")
        self.bad("2027-13-01", THU, "no_such_date")

    def test_month_names(self):
        self.ok("march 20", THU, "2027-03-20")
        self.ok("Mar 20th", THU, "2027-03-20")
        self.ok("20 march", THU, "2027-03-20")
        self.ok("the 20th of March", THU, "2027-03-20")
        self.ok("march 11", THU, "2027-03-11")                     # today counts
        w = self.ok("march 10", THU, "2028-03-10")                 # passed -> next year, and says so
        self.assertTrue(w.notes)
        self.ok("December 1st, 2027", THU, "2027-12-01")
        self.ok("sept 3", THU, "2027-09-03")
        self.bad("february 30", THU, "no_such_date")
        self.bad("april 31", THU, "no_such_date")
        self.bad("feb 29", THU, "no_such_date")                    # 2027 is not a leap year
        self.ok("feb 29", at(2028, 1, 10), "2028-02-29")
        self.ok("feb 29 2028", THU, "2028-02-29")

    def test_day_of_month(self):
        self.ok("the 31st", THU, "2027-03-31")
        self.ok("the 11th", THU, "2027-03-11")
        w = self.ok("the 5th", THU, "2027-04-05")
        self.assertTrue(w.notes)
        self.bad("the 31st", at(2027, 4, 10), "no_such_date")      # 30-day month
        self.bad("the 30th", at(2027, 2, 10), "no_such_date")
        self.bad("the 31st", at(2027, 3, 31) .replace(day=31, month=5) and at(2027, 6, 1), "no_such_date")
        self.bad("the 30th", at(2027, 1, 31), "no_such_date")      # passed, and February has no 30th
        self.ok("the 1st", at(2026, 12, 15), "2027-01-01")

    def test_numeric(self):
        self.ok("3/20", THU, "2027-03-20")
        self.ok("3/20/2028", THU, "2028-03-20")
        self.ok("20/3", THU, "2027-03-20")
        self.bad("3/4", THU, "ambiguous_numeric_date")
        self.bad("13/13", THU, "no_such_date")

    def test_month_and_year_boundaries(self):
        self.ok("end of the month", THU, "2027-03-31")
        self.ok("end of month", at(2027, 4, 30), "2027-04-30")
        self.ok("end of the month", at(2027, 2, 3), "2027-02-28")
        self.ok("end of the month", at(2028, 2, 3), "2028-02-29")
        self.ok("end of next month", THU, "2027-04-30")
        self.ok("end of next month", at(2026, 12, 5), "2027-01-31")
        self.ok("start of next month", at(2026, 12, 5), "2027-01-01")
        self.ok("end of the year", THU, "2027-12-31")
        self.bad("end of the week", THU, "ambiguous_range")

    def test_not_a_single_day(self):
        for expr in ("next week", "this weekend", "next month", "the weekend"):
            self.bad(expr, THU, "ambiguous_range")
        self.bad("soon", THU, "vague_date")
        self.bad("whenever works", THU, "unknown_date")
        self.bad("", THU, "empty")
        self.bad("   ", THU, "empty")

    def test_case_spacing_and_punctuation(self):
        self.ok("  FRIDAY,  3 to 4 PM. ", THU, "2027-03-12", "15:00", "16:00")
        self.ok("Friday at 3 p.m.", THU, "2027-03-12", "15:00")
        self.ok("tomorrow 9–11am", THU, "2027-03-12", "09:00", "11:00")   # en dash


class Times(Base):
    def test_single_times(self):
        for expr, t in [("3pm", "15:00"), ("3 pm", "15:00"), ("3:30pm", "15:30"), ("9am", "09:00"), ("15:00", "15:00"),
                        ("9:05", "09:05"), ("noon", "12:00"), ("midnight", "00:00"), ("12:30pm", "12:30"), ("12:30am", "00:30"),
                        ("at 7pm", "19:00"), ("00:00", "00:00"), ("23:59", "23:59"), ("11:59pm", "23:59"), ("17", "17:00")]:
            self.assertEqual(parse_time(expr), (t, None), expr)

    def test_bad_times(self):
        for expr, code in [("12pm", "ambiguous_12"), ("12am", "ambiguous_12"), ("12:00pm", "ambiguous_12"), ("3", "ambiguous_ampm"),
                           ("25:00", "bad_time"), ("13pm", "bad_time"), ("9:75", "bad_time"), ("morning", "vague_time"),
                           ("in the evening", "vague_time"), ("banana", "bad_time"), ("", "empty"), ("3 to 4", "ambiguous_ampm"),
                           ("0pm", "bad_time")]:
            with self.assertRaises(WhenError, msg=expr) as cm:
                parse_time(expr)
            self.assertEqual(cm.exception.code, code, expr)

    def test_ranges(self):
        for expr, s, e in [("3 to 4pm", "15:00", "16:00"), ("3-4pm", "15:00", "16:00"), ("3pm to 4pm", "15:00", "16:00"),
                           ("from 9am until 11:30am", "09:00", "11:30"), ("11 to 1pm", "11:00", "13:00"),
                           ("11am to 1", "11:00", "13:00"), ("9am-5pm", "09:00", "17:00"), ("14:00-15:30", "14:00", "15:30"),
                           ("12 to 1pm", "12:00", "13:00"), ("noon to 2pm", "12:00", "14:00"), ("8 to 9:30am", "08:00", "09:30"),
                           ("2:30-3:15pm", "14:30", "15:15"), ("10 to 11am", "10:00", "11:00"), ("9am to 5", "09:00", "17:00")]:
            self.assertEqual(parse_time(expr), (s, e), expr)

    def test_the_benchmark_failure(self):
        # the first benchmark's model turned "3 to 4pm" into 16:00-17:00
        self.ok("tomorrow", WED, "2026-11-19", "15:00", "16:00", time_text="3 to 4pm")

    def test_bad_ranges(self):
        for expr, code in [("10pm to 2am", "crosses_midnight"), ("11pm to 1am", "crosses_midnight"), ("3pm to 3pm", "empty_range"),
                           ("5pm to 4pm", "crosses_midnight"), ("10 to 2am", "crosses_midnight"), ("9 to 5", "ambiguous_ampm"),
                           ("11am to 12pm", "ambiguous_12"), ("10pm to 2", "crosses_midnight")]:
            with self.assertRaises(WhenError, msg=expr) as cm:
                parse_time(expr)
            self.assertEqual(cm.exception.code, code, expr)

    def test_durations(self):
        self.ok("monday 2pm for 45 minutes", THU, "2027-03-15", "14:00", "14:45")
        self.ok("tomorrow 9am for an hour", THU, "2027-03-12", "09:00", "10:00")
        self.ok("tomorrow 9am for an hour and a half", THU, "2027-03-12", "09:00", "10:30")
        self.ok("tomorrow 10:15 for 2 hours", THU, "2027-03-12", "10:15", "12:15")
        self.bad("tomorrow 11pm for 2 hours", THU, "crosses_midnight")

    def test_date_with_time(self):
        self.ok("tomorrow 3pm", THU, "2027-03-12", "15:00")
        self.ok("tomorrow at 3pm", THU, "2027-03-12", "15:00")
        self.ok("3pm tomorrow", THU, "2027-03-12", "15:00")
        self.ok("friday at noon", THU, "2027-03-12", "12:00")
        self.ok("next tuesday 14:30", THU, "2027-03-16", "14:30")
        self.ok("march 20 at 8am", THU, "2027-03-20", "08:00")
        self.ok("in 3 days at 5pm", THU, "2027-03-14", "17:00")
        self.bad("3pm", THU, "missing_date")
        self.bad("tomorrow 12pm", THU, "ambiguous_12")

    def test_separate_fields(self):
        self.ok("friday", THU, "2027-03-12", "15:00", "16:00", time_text="3pm", end_text="4pm")
        self.ok("friday", THU, "2027-03-12", "15:00", "16:00", time_text="15:00", end_text="16:00")
        self.ok("friday 3pm", THU, "2027-03-12", "15:00", "16:00", end_text="4pm")
        self.ok("friday 3pm", THU, "2027-03-12", "15:00", time_text="15:00")           # same thing twice is fine
        self.bad("friday 3pm", THU, "conflict", time_text="4pm")
        self.bad("friday", THU, "crosses_midnight", time_text="3pm", end_text="2pm")
        self.bad("friday", THU, "empty_range", time_text="3pm", end_text="3pm")
        self.bad("friday", THU, "missing_time", end_text="4pm")
        self.bad("friday", THU, "ambiguous_ampm", time_text="3")
        self.bad("friday", THU, "vague_time", time_text="morning")

    def test_part_of_day_sets_no_time(self):
        w = self.ok("tomorrow morning", THU, "2027-03-12")
        self.assertIn("morning", w.notes[0])
        self.ok("tonight", THU, "2027-03-11")
        self.ok("friday afternoon", THU, "2027-03-12")


class OffsetsAndDst(Base):
    def test_elapsed_offsets(self):
        self.ok("in two hours", THU, "2027-03-11", "18:40")
        self.ok("in 2 hours", THU, "2027-03-11", "18:40")
        self.ok("in 90 minutes", THU, "2027-03-11", "18:10")
        self.ok("in half an hour", THU, "2027-03-11", "17:10")
        self.ok("an hour from now", THU, "2027-03-11", "17:40")
        self.ok("in an hour and a half", THU, "2027-03-11", "18:10")
        self.ok("in 1 hour and 15 minutes", THU, "2027-03-11", "17:55")
        self.ok("in 8 hours", THU, "2027-03-12", "00:40")                  # rolls to the next day
        self.ok("in 30 minutes", at(2026, 12, 31, 23, 45), "2027-01-01", "00:15")   # rolls to the next year
        self.bad("in two hours", THU, "conflict", time_text="5pm")

    def test_spring_forward(self):
        # America/Chicago: 2027-03-14 02:00 CST -> 03:00 CDT
        self.bad("sunday 2:30am", THU, "nonexistent_local_time")
        self.bad("2027-03-14 02:00", THU, "nonexistent_local_time")
        self.ok("sunday 1:59am", THU, "2027-03-14", "01:59")
        self.ok("sunday 3am", THU, "2027-03-14", "03:00")
        self.bad("sunday 1:30am to 2:30am", THU, "nonexistent_local_time")
        # elapsed time is exact across the change: 01:30 CST + 2h = 04:30 CDT
        self.ok("in two hours", at(2027, 3, 14, 1, 30), "2027-03-14", "04:30")
        # 23:30 on the 13th + 24h of elapsed time is 00:30 on the 15th
        self.ok("in 24 hours", at(2027, 3, 13, 23, 30), "2027-03-15", "00:30")
        # day arithmetic is by the calendar, not by 24-hour blocks
        self.ok("tomorrow", at(2027, 3, 13, 23, 30), "2027-03-14")
        self.ok("in 2 days", at(2027, 3, 13, 23, 30), "2027-03-15")

    def test_fall_back(self):
        # America/Chicago: 2027-11-07 02:00 CDT -> 01:00 CST, so 01:30 happens twice
        now = at(2027, 11, 5, 9, 0)
        self.bad("sunday 1:30am", now, "ambiguous_local_time")
        self.ok("sunday 12:59am", now, "2027-11-07", "00:59")
        self.ok("sunday 2am", now, "2027-11-07", "02:00")
        first = datetime(2027, 11, 7, 0, 30, tzinfo=CHI)
        self.ok("in two hours", first, "2027-11-07", "01:30")              # 00:30 CDT + 2h = 01:30 CST
        self.ok("in 3 hours", first, "2027-11-07", "02:30")

    def test_other_zones(self):
        syd = ZoneInfo("Australia/Sydney")          # southern hemisphere: DST ends 2027-04-04 03:00 -> 02:00
        self.bad("2027-04-04 02:30", datetime(2027, 4, 1, 9, 0, tzinfo=syd), "ambiguous_local_time")
        utc = ZoneInfo("UTC")
        self.ok("2027-03-14 02:30", datetime(2027, 3, 11, 9, 0, tzinfo=utc), "2027-03-14", "02:30")
        self.ok("friday", WED, "2026-11-20")
        self.ok("sunday", WED, "2026-11-22")

    def test_now_must_be_aware(self):
        with self.assertRaises(TypeError):
            parse_when("friday", datetime(2027, 3, 11, 16, 40))

    def test_human_date_is_locale_independent(self):
        self.assertEqual(human_date("2027-03-11"), "Thursday, March 11, 2027")
        self.assertEqual(parse_when("friday", THU).weekday, "Friday")


if __name__ == "__main__":
    unittest.main()
