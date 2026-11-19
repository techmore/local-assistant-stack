# SPDX-License-Identifier: MIT
"""Third-round tool fixes behind World(v3=True): anchored offsets and overnight events through the
tool layer, no blind retry after a failed send or delete, thread lookup by number, and the v3 prompt.
Each class also checks that the earlier behaviour is unchanged when the switch is off."""
import json
import unittest
from datetime import datetime, timedelta, timezone

import _path  # noqa: F401
import gate
import state
import tools


class Clock:
    def __init__(self):
        self.t = datetime(2027, 3, 11, 22, 40, tzinfo=timezone.utc)

    def __call__(self):
        return self.t

    def tick(self, **kw):
        self.t += timedelta(**kw)


def world(v3=True, **kw):
    clock, store = Clock(), state.MemoryStore()
    w = tools.World(fixture_name="heldout", gate=True, nl_dates=True, v3=v3, store=store, clock=clock, device_id="test-tools", **kw)
    return w, gate.Approver(store, "test-user", clock=clock), clock


class DatesThroughTools(unittest.TestCase):
    def test_reminder_the_day_before_a_date(self):
        w, _, _ = world()
        r = w.call("reminder_create", {"text": "Pack my bag", "due_date": "the day before 2027-04-02"})
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["reminder"]["due_date"], "2027-04-01")
        self.assertEqual(w.calls[-1]["norm"]["due_date"], "2027-04-01")
        self.assertIn("1 day before 2027-04-02 (Friday)", r["resolved"]["notes"])

    def test_reminder_an_hour_before_a_time(self):
        w, _, _ = world()
        r = w.call("reminder_create", {"text": "Leave the house", "due_date": "saturday", "due_time": "1 hour before 2:15pm"})
        self.assertEqual((r["reminder"]["due_date"], r["reminder"]["due_time"]), ("2027-03-13", "13:15"))

    def test_unknown_anchor_is_relayed(self):
        w, _, _ = world()
        r = w.call("reminder_create", {"text": "Pack", "due_date": "the day before departure"})
        self.assertEqual(r["code"], "unknown_anchor")
        self.assertEqual(len(w.reminders), w.base["reminders"])

    def test_overnight_event_is_one_event_with_an_end_date(self):
        w, _, _ = world()
        r = w.call("calendar_create_event", {"title": "Night shift", "date": "friday", "start_time": "10pm to 2am"})
        self.assertTrue(r["ok"], r)
        ev = r["event"]
        self.assertEqual((ev["date"], ev["start_time"], ev["end_time"], ev["end_date"]), ("2027-03-12", "22:00", "02:00", "2027-03-13"))
        self.assertEqual(r["resolved"]["end_date"], "2027-03-13")
        self.assertEqual(len(w.calendar), w.base["events"] + 1)
        sat = w.call("calendar_list_events", {"date": "saturday"})
        self.assertIn("Night shift", [e["title"] for e in sat["events"]])

    def test_event_ending_at_midnight(self):
        w, _, _ = world()
        r = w.call("calendar_create_event", {"title": "Late film", "date": "friday", "start_time": "10pm", "end_time": "12am"})
        self.assertEqual((r["event"]["end_time"], r["event"]["end_date"]), ("00:00", "2027-03-13"))
        sat = w.call("calendar_list_events", {"date": "saturday"})   # it ends as Saturday starts: not a Saturday event
        self.assertNotIn("Late film", [e["title"] for e in sat["events"]])

    def test_same_day_event_has_no_end_date(self):
        w, _, _ = world()
        r = w.call("calendar_create_event", {"title": "Reports", "date": "monday", "start_time": "3 to 4pm"})
        self.assertNotIn("end_date", r["event"])

    def test_switch_off_keeps_the_measured_behaviour(self):
        w, _, _ = world(v3=False)
        self.assertEqual(w.call("calendar_create_event", {"title": "Night shift", "date": "friday", "start_time": "10pm to 2am"})["code"], "crosses_midnight")
        self.assertEqual(w.call("reminder_create", {"text": "Pack", "due_date": "the day before 2027-04-02"})["code"], "unknown_date")
        self.assertEqual(len(w.calendar), w.base["events"])


class NoBlindRetry(unittest.TestCase):
    FAIL = {"send_message:execute": {"error": "delivery failed: no signal"}}

    def _stage_and_approve(self, w, ap, args):
        r = w.call("send_message", args)
        self.assertEqual(r["status"], "confirmation_required", r)
        ap.approve(r["confirmation_id"])
        return r["confirmation_id"]

    def test_failed_send_says_do_not_retry(self):
        w, ap, _ = world(overrides=self.FAIL)
        cid = self._stage_and_approve(w, ap, {"to": "Tobias", "body": "I'm in for Sunday"})
        r = w.call("send_message", {"confirmation_id": cid})
        self.assertEqual((r["error"], r["executed"], r["retry"]), ("failed", False, False))
        self.assertIn("no signal", r["reason"])
        self.assertIn("NOT sent", r["message"])
        self.assertEqual(w.sent, [])
        self.assertEqual(w.executed, [])
        self.assertEqual(w.gate.get(cid)["status"], "failed")

    def test_the_same_confirmation_cannot_be_used_again(self):
        w, ap, _ = world(overrides=self.FAIL)
        cid = self._stage_and_approve(w, ap, {"to": "Tobias", "body": "I'm in for Sunday"})
        w.call("send_message", {"confirmation_id": cid})
        w.overrides = {}  # even if the network came back, the old approval is closed
        r = w.call("send_message", {"confirmation_id": cid})
        self.assertEqual((r["error"], r["executed"]), ("already_failed", False))
        self.assertEqual(w.sent, [])

    def test_the_same_message_is_not_staged_again_right_away(self):
        w, ap, clock = world(overrides=self.FAIL)
        cid = self._stage_and_approve(w, ap, {"to": "Tobias", "body": "I'm in for Sunday"})
        w.call("send_message", {"confirmation_id": cid})
        r = w.call("send_message", {"to": "Tobias", "body": "I'm in for Sunday"})
        self.assertEqual((r["error"], r["retry"]), ("recently_failed", False))
        self.assertEqual(ap.pending(), [])
        # a different message is a new request
        self.assertEqual(w.call("send_message", {"to": "Tobias", "body": "Call me"})["status"], "confirmation_required")
        # and after the cool-off the user can ask again
        clock.tick(seconds=tools.RETRY_COOLDOWN_S + 1)
        self.assertEqual(w.call("send_message", {"to": "Tobias", "body": "I'm in for Sunday"})["status"], "confirmation_required")

    def test_retry_after_cooloff_can_succeed(self):
        w, ap, clock = world(overrides=self.FAIL)
        cid = self._stage_and_approve(w, ap, {"to": "Tobias", "body": "I'm in for Sunday"})
        w.call("send_message", {"confirmation_id": cid})
        clock.tick(seconds=tools.RETRY_COOLDOWN_S + 1)
        w.overrides = {}
        cid2 = self._stage_and_approve(w, ap, {"to": "Tobias", "body": "I'm in for Sunday"})
        self.assertNotEqual(cid, cid2)
        self.assertEqual(w.call("send_message", {"confirmation_id": cid2})["status"], "sent")
        self.assertEqual(len(w.sent), 1)

    def test_failed_delete(self):
        w, ap, _ = world(overrides={"file_delete:execute": {"error": "volume is read-only"}})
        r = w.call("file_delete", {"path": "scratch-notes.txt"})
        ap.approve(r["confirmation_id"])
        r2 = w.call("file_delete", {"confirmation_id": r["confirmation_id"]})
        self.assertEqual((r2["error"], r2["retry"]), ("failed", False))
        self.assertIn("scratch-notes.txt", w.files)
        self.assertEqual(w.call("file_delete", {"path": "scratch-notes.txt"})["error"], "recently_failed")

    def test_failed_event_without_approval_changes_nothing(self):
        clock, store = Clock(), state.MemoryStore()
        g = gate.Gate(store, "tools", clock=clock)
        rec = g.stage("send_message", {"p": 1}, {"to": "555-0100", "body": "x", "channel": "sms"})
        g.failed(rec["confirmation_id"])
        self.assertEqual(g.get(rec["confirmation_id"])["status"], "pending")

    def test_switch_off_keeps_the_measured_behaviour(self):
        w, ap, _ = world(v3=False, overrides=self.FAIL)
        cid = self._stage_and_approve(w, ap, {"to": "Tobias", "body": "I'm in for Sunday"})
        r = w.call("send_message", {"confirmation_id": cid})
        self.assertEqual(r, {"error": "delivery failed: no signal"})
        self.assertEqual(w.gate.get(cid)["status"], "approved")


class ThreadLookupByNumber(unittest.TestCase):
    def test_thread_by_number_not_in_contacts(self):
        w, _, _ = world()
        r = w.call("messages_get_thread", {"contact": "555-0199"})
        self.assertTrue(r["messages"])

    def test_contacts_lookup_points_to_the_thread_tool(self):
        w, _, _ = world()
        r = w.call("contacts_lookup", {"name": "555-0199"})
        self.assertEqual(r["count"], 0)
        self.assertIn("messages_get_thread", r["note"])
        self.assertNotIn("note", w.call("contacts_lookup", {"name": "Marisol"}))
        w0, _, _ = world(v3=False)
        self.assertNotIn("note", w0.call("contacts_lookup", {"name": "555-0199"}))

    def test_descriptions(self):
        def desc(v3):
            return {s["function"]["name"]: s["function"] for s in tools.schemas("explicit_strict", gate=True, nl_dates=True, v3=v3)}
        new, old = desc(True), desc(False)
        self.assertIn("phone number", new["messages_get_thread"]["description"])
        self.assertIn("without looking it up", new["messages_get_thread"]["description"])
        self.assertIn("the day before 2027-04-02", new["reminder_create"]["parameters"]["properties"]["due_date"]["description"])
        self.assertIn("1 hour before 2:15pm", new["reminder_create"]["parameters"]["properties"]["due_time"]["description"])
        self.assertIn("past midnight", new["calendar_create_event"]["description"])
        self.assertIn("did NOT happen", new["send_message"]["description"])
        self.assertIn("did NOT happen", new["file_delete"]["description"])
        for name, fn in old.items():   # nothing of the new text leaks into the earlier schemas
            blob = json.dumps(fn)
            for marker in ("the day before", "past midnight", "did NOT happen", "without looking it up"):
                self.assertNotIn(marker, blob, name)
        self.assertEqual(json.dumps(tools.schemas("explicit_strict", gate=True, nl_dates=True)),
                         json.dumps(tools.schemas("explicit_strict", gate=True, nl_dates=True, v3=False)))

    def test_v3_without_the_other_switches_does_not_break_the_schemas(self):
        for g in (False, True):
            for nl in (False, True):
                for variant in ("plain", "explicit", "strict", "explicit_strict"):
                    out = tools.schemas(variant, gate=g, nl_dates=nl, v3=True)
                    self.assertEqual(len(out), len(tools.TOOL_NAMES))


class PromptV3(unittest.TestCase):
    def setUp(self):
        import runner
        self.blocks = runner.prompt_blocks(tools.fixture("heldout"))
        self.hermes = runner.prompt_blocks(tools.fixture("heldout"), "mcp__lab__")

    def test_v3_prompt_has_no_copyable_arithmetic_answer(self):
        p = self.blocks["rules3"] + self.blocks["fewshot3"]
        self.assertNotIn("12% of 250", p)
        self.assertNotIn('answer "30"', p)
        self.assertIn("the day before 2027-05-04", p)
        self.assertIn("pass them to the tools as given", p)
        self.assertIn('"Text", "email" or "send" means send', p)

    def test_tool_prefix(self):
        self.assertNotIn("mcp__lab__", self.blocks["fewshot3"])
        self.assertIn("mcp__lab__reminder_create", self.hermes["fewshot3"])

    def test_v2_prompt_is_untouched(self):
        self.assertIn("12% of 250", self.blocks["fewshot2"])
        self.assertNotIn("the day before", self.blocks["rules2"])


if __name__ == "__main__":
    unittest.main()
