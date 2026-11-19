# SPDX-License-Identifier: MIT
"""Third-round resolver additions: offsets anchored on a known date or time, and ranges past midnight.
Both are opt-in (anchored=True / overnight=True); the last class checks that the defaults did not move."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import _path  # noqa: F401
from dates import WhenError, parse_time, parse_when

NOW = datetime(2027, 3, 11, 16, 40, tzinfo=ZoneInfo("America/Chicago"))  # a Thursday


def when(text, time=None, end=None, **kw):
    kw.setdefault("anchored", True)
    kw.setdefault("overnight", True)
    w = parse_when(text, NOW, time, end, **kw)
    return w.date, w.time, w.end_time, w.end_date


class AnchoredDates(unittest.TestCase):
    def test_day_offsets_from_a_date(self):
        for text, date in [
            ("the day before 2027-04-02", "2027-04-01"),
            ("1 day before april 2", "2027-04-01"),
            ("one day before April 2, 2027", "2027-04-01"),
            ("the day before april 1", "2027-03-31"),          # crosses a month boundary
            ("the day after 2027-12-31", "2028-01-01"),        # crosses a year boundary
            ("2 days after friday", "2027-03-14"),
            ("3 days before the 20th", "2027-03-17"),
            ("a week before march 20", "2027-03-13"),
            ("two weeks after 2027-03-20", "2027-04-03"),
            ("the night before april 2", "2027-04-01"),
            ("the day before the end of the month", "2027-03-30"),
            ("a month after 2027-01-15", "2027-02-15"),
            ("the day prior to 2027-04-02", "2027-04-01"),
        ]:
            self.assertEqual(when(text), (date, None, None, None), text)

    def test_time_can_ride_along(self):
        self.assertEqual(when("the day before 2027-04-02 at 9am"), ("2027-04-01", "09:00", None, None))
        self.assertEqual(when("9am the day before april 2"), ("2027-04-01", "09:00", None, None))
        self.assertEqual(when("the day before 2027-04-02", "8:30pm"), ("2027-04-01", "20:30", None, None))

    def test_note_shows_the_arithmetic(self):
        w = parse_when("the day before 2027-04-02", NOW, anchored=True)
        self.assertIn("1 day before 2027-04-02 (Friday)", w.notes)

    def test_anchor_must_be_a_date(self):
        for text in ("the day before departure", "2 days before the trip", "the day after it's due"):
            with self.assertRaises(WhenError) as cm:
                when(text)
            self.assertEqual(cm.exception.code, "unknown_anchor", text)
            self.assertIn("actual date", str(cm.exception))

    def test_anchor_errors_keep_their_own_code(self):
        with self.assertRaises(WhenError) as cm:
            when("the day before next week")
        self.assertEqual(cm.exception.code, "ambiguous_range")
        with self.assertRaises(WhenError) as cm:
            when("a month before 2027-05-31")   # April has 30 days
        self.assertEqual(cm.exception.code, "no_such_date")


class AnchoredTimes(unittest.TestCase):
    def test_offset_in_the_time_field(self):
        self.assertEqual(when("saturday", "1 hour before 2:15pm"), ("2027-03-13", "13:15", None, None))
        self.assertEqual(when("saturday", "an hour and a half before 2:15pm"), ("2027-03-13", "12:45", None, None))
        self.assertEqual(when("saturday", "45 minutes after noon"), ("2027-03-13", "12:45", None, None))
        self.assertEqual(when("2027-03-13", "half an hour before 14:15"), ("2027-03-13", "13:45", None, None))

    def test_offset_in_the_date_field(self):
        for text in ("1 hour before 2:15pm saturday", "saturday 1 hour before 2:15pm", "one hour before 2:15pm on saturday"):
            self.assertEqual(when(text), ("2027-03-13", "13:15", None, None), text)

    def test_offset_can_move_to_the_previous_or_next_day(self):
        self.assertEqual(when("friday", "30 minutes before 12:10am"), ("2027-03-11", "23:40", None, None))
        self.assertEqual(when("friday", "2 hours after 11pm"), ("2027-03-13", "01:00", None, None))

    def test_needs_a_clock_time_and_a_day(self):
        for args, code in [(("saturday", "1 hour before"), "unknown_anchor"),
                           (("1 hour before 2:15pm",), "missing_date"),
                           (("saturday", "1 hour before 2 to 3pm"), "unknown_anchor"),
                           (("saturday", "1 hour before 2:15pm", "4pm"), "unknown_anchor")]:
            with self.assertRaises(WhenError) as cm:
                when(*args)
            self.assertEqual(cm.exception.code, code, args)

    def test_result_is_checked_against_daylight_saving(self):
        # clocks jump from 02:00 to 03:00 on Sunday 2027-03-14 in America/Chicago
        with self.assertRaises(WhenError) as cm:
            when("sunday", "1 hour before 3:30am")
        self.assertEqual(cm.exception.code, "nonexistent_local_time")


class Overnight(unittest.TestCase):
    def test_ranges_past_midnight(self):
        for args, want in [
            (("friday", "10pm to 2am"), ("2027-03-12", "22:00", "02:00", "2027-03-13")),
            (("friday 10pm to 2am",), ("2027-03-12", "22:00", "02:00", "2027-03-13")),
            (("friday", "10pm", "2am"), ("2027-03-12", "22:00", "02:00", "2027-03-13")),
            (("friday", "22:00-02:00"), ("2027-03-12", "22:00", "02:00", "2027-03-13")),
            (("friday", "9pm to 1"), ("2027-03-12", "21:00", "01:00", "2027-03-13")),
            (("friday", "10 to 2am"), ("2027-03-12", "22:00", "02:00", "2027-03-13")),
            (("friday", "11pm for 2 hours"), ("2027-03-12", "23:00", "01:00", "2027-03-13")),
        ]:
            self.assertEqual(when(*args), want, args)

    def test_midnight_as_a_boundary(self):
        for args, want in [
            (("friday", "10pm to midnight"), ("2027-03-12", "22:00", "00:00", "2027-03-13")),
            (("friday", "10pm to 12am"), ("2027-03-12", "22:00", "00:00", "2027-03-13")),
            (("friday", "10pm", "midnight"), ("2027-03-12", "22:00", "00:00", "2027-03-13")),
            (("friday", "10pm", "12am"), ("2027-03-12", "22:00", "00:00", "2027-03-13")),
            (("friday", "10pm for 2 hours"), ("2027-03-12", "22:00", "00:00", "2027-03-13")),
            (("saturday", "12am to 2am"), ("2027-03-13", "00:00", "02:00", None)),
            (("saturday", "midnight to 2am"), ("2027-03-13", "00:00", "02:00", None)),
            (("friday", "11am to 12pm"), ("2027-03-12", "11:00", "12:00", None)),
        ]:
            self.assertEqual(when(*args), want, args)

    def test_same_day_ranges_are_unchanged(self):
        for args, want in [(("friday", "3 to 4pm"), ("15:00", "16:00")), (("friday", "11 to 1pm"), ("11:00", "13:00")),
                           (("friday", "11am to 1"), ("11:00", "13:00")), (("friday", "2pm for 45 minutes"), ("14:00", "14:45"))]:
            d, s, e, ed = when(*args)
            self.assertEqual((s, e, ed), (*want, None), args)

    def test_still_rejected(self):
        for args, code in [(("friday", "12pm"), "ambiguous_12"),          # a lone 12 is still not guessed
                           (("friday", "12am"), "ambiguous_12"),
                           (("friday", "3 to 4"), "ambiguous_ampm"),
                           (("friday", "2pm to 1pm"), "too_long"),          # 23 hours: an am/pm slip
                           (("friday", "3pm", "2pm"), "too_long"),
                           (("friday", "3pm to 3pm"), "empty_range")]:
            with self.assertRaises(WhenError) as cm:
                when(*args)
            self.assertEqual(cm.exception.code, code, args)

    def test_end_on_the_next_day_is_checked_against_daylight_saving(self):
        with self.assertRaises(WhenError) as cm:
            when("saturday", "11pm to 2:30am")   # 02:30 on Sunday 2027-03-14 does not exist
        self.assertEqual(cm.exception.code, "nonexistent_local_time")

    def test_note_names_the_end_day(self):
        w = parse_when("friday", NOW, "10pm to 2am", overnight=True)
        self.assertTrue(any("Saturday 2027-03-13" in n for n in w.notes), w.notes)


class DefaultsDidNotMove(unittest.TestCase):
    """Earlier configurations call parse_when without the new switches and must behave as measured."""

    def test_overnight_is_rejected_by_default(self):
        for args in (("friday", "10pm to 2am"), ("friday", "10pm", "2am"), ("friday", "11pm for 2 hours")):
            with self.assertRaises(WhenError) as cm:
                parse_when(args[0], NOW, *args[1:])
            self.assertEqual(cm.exception.code, "crosses_midnight", args)
        with self.assertRaises(WhenError) as cm:
            parse_when("friday", NOW, "10pm to 12am")
        self.assertEqual(cm.exception.code, "ambiguous_12")

    def test_anchors_are_unknown_by_default(self):
        with self.assertRaises(WhenError) as cm:
            parse_when("the day before 2027-04-02", NOW)
        self.assertEqual(cm.exception.code, "unknown_date")
        with self.assertRaises(WhenError):
            parse_when("saturday", NOW, "1 hour before 2:15pm")

    def test_parse_time_signature(self):
        self.assertEqual(parse_time("3 to 4pm"), ("15:00", "16:00"))
        self.assertEqual(parse_time("10pm to 2am", overnight=True, full=True), ("22:00", "02:00", 1))
        self.assertEqual(parse_time("12am", allow12=True), ("00:00", None))
        when_default = parse_when("friday", NOW, "3 to 4pm")
        self.assertIsNone(when_default.end_date)


if __name__ == "__main__":
    unittest.main()
