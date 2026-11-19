# SPDX-License-Identifier: MIT
"""Confirmation gate, event store and tool-layer enforcement. No model, no network, no OS specifics."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import _path  # noqa: F401
import gate
import state
import tools


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 18, 18, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.t

    def tick(self, **kw):
        self.t += timedelta(**kw)


def world(**kw):
    clock = kw.pop("clock", None) or Clock()
    store = kw.pop("store", None) or state.MemoryStore()
    w = tools.World(gate=True, store=store, clock=clock, device_id="test-tools", **kw)
    return w, gate.Approver(store, "test-user", clock=clock), clock


class GateOnly(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.store = state.MemoryStore()
        self.g = gate.Gate(self.store, "dev-a", clock=self.clock)
        self.ap = gate.Approver(self.store, "dev-b", clock=self.clock)

    def stage(self):
        return self.g.stage("send_message", {"p": 1}, {"to": "555-0100", "body": "hi", "channel": "sms"})

    def test_nothing_redeems_without_a_decision(self):
        r = self.stage()
        for _ in range(3):
            ok, err = self.g.redeem(r["confirmation_id"], "send_message")
            self.assertFalse(ok)
            self.assertEqual(err["error"], "not_confirmed")

    def test_approve_then_redeem_once(self):
        cid = self.stage()["confirmation_id"]
        self.ap.approve(cid)
        ok, rec = self.g.redeem(cid, "send_message")
        self.assertTrue(ok)
        self.assertEqual(rec["decided_by"], "dev-b")
        self.assertEqual(rec["created_by"], "dev-a")
        self.g.executed(cid)
        ok, err = self.g.redeem(cid, "send_message")
        self.assertEqual((ok, err["error"]), (False, "already_used"))

    def test_decline_is_final_and_first_decision_wins(self):
        cid = self.stage()["confirmation_id"]
        self.ap.decline(cid)
        rec = self.ap.approve(cid)                       # a second device approving later changes nothing
        self.assertEqual(rec["status"], "declined")
        self.assertEqual(rec["ignored"][0]["why"], "already_decided")
        self.assertEqual(self.g.redeem(cid, "send_message")[1]["error"], "declined")
        cid2 = self.g.stage("send_message", {"p": 2}, {"to": "555-0101", "body": "x", "channel": "sms"})["confirmation_id"]
        self.ap.approve(cid2)
        self.assertEqual(self.ap.decline(cid2)["status"], "approved")
        self.ap.approve(cid2)                            # approving twice is idempotent
        self.assertTrue(self.g.redeem(cid2, "send_message")[0])

    def test_expiry(self):
        cid = self.stage()["confirmation_id"]
        self.clock.tick(minutes=16)
        self.assertEqual(self.ap.approve(cid)["status"], "expired")     # approval arriving after expiry is ignored
        self.assertEqual(self.g.redeem(cid, "send_message")[1]["error"], "expired")
        cid2 = self.g.stage("send_message", {"p": 3}, {"to": "555-0102", "body": "y", "channel": "sms"})["confirmation_id"]
        self.ap.approve(cid2)
        self.clock.tick(minutes=16)                      # approved in time but not used in time
        self.assertEqual(self.g.redeem(cid2, "send_message")[1]["error"], "expired")

    def test_unknown_id_and_wrong_kind(self):
        self.assertEqual(self.g.redeem("cf-000000000000", "send_message")[1]["error"], "unknown_confirmation_id")
        cid = self.stage()["confirmation_id"]
        self.ap.approve(cid)
        self.assertEqual(self.g.redeem(cid, "file_delete")[1]["error"], "unknown_confirmation_id")

    def test_ids_are_unguessable_and_staging_is_idempotent(self):
        a, b = self.stage(), self.stage()
        self.assertEqual(a["confirmation_id"], b["confirmation_id"])
        c = self.g.stage("send_message", {"p": 1}, {"to": "555-0100", "body": "other", "channel": "sms"})
        self.assertNotEqual(a["confirmation_id"], c["confirmation_id"])
        self.assertRegex(a["confirmation_id"], r"^cf-[0-9a-f]{12}$")

    def test_executed_without_approval_is_ignored_by_the_reducer(self):
        cid = self.stage()["confirmation_id"]
        self.store.append(state.make_event("executed", cid, "rogue"))
        rec = state.reduce(self.store.events(), self.clock())[cid]
        self.assertEqual(rec["status"], "pending")
        self.assertEqual(rec["ignored"][0]["why"], "executed_without_approval")

    def test_store_failure_fails_closed(self):
        class Down:
            def events(self):
                raise state.StoreUnavailable("hub unreachable")

            def append(self, ev):
                raise state.StoreUnavailable("hub unreachable")
        g = gate.Gate(Down(), "dev-a")
        self.assertEqual(g.redeem("cf-123456789abc", "send_message"), (False, {"error": "gate_unavailable", "message": g.redeem("cf-123456789abc", "send_message")[1]["message"]}))
        w = tools.World(gate=True, store=Down())
        r = w.call("send_message", {"to": "Dana", "body": "hi"})
        self.assertEqual(r["error"], "gate_unavailable")
        self.assertEqual((w.sent, w.executed), ([], []))


class EventFormat(unittest.TestCase):
    def test_events_are_versioned_utc_and_carry_a_device(self):
        w, ap, _ = world()
        cid = w.call("send_message", {"to": "Dana", "body": "hi"})["confirmation_id"]
        ap.approve(cid)
        w.call("send_message", {"confirmation_id": cid})
        evs = w.gate.store.events()
        self.assertEqual([e["type"] for e in evs], ["pending", "decision", "executed"])
        for e in evs:
            self.assertEqual(e["v"], state.SCHEMA_VERSION)
            self.assertTrue(e["device_id"])
            self.assertRegex(e["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z$")
            self.assertEqual(len(e["event_id"]), 32)
            text = json.dumps(e)
            self.assertNotIn(str(Path.home()), text)        # no absolute local paths in records
        self.assertEqual(len({e["event_id"] for e in evs}), 3)
        self.assertEqual({e["device_id"] for e in evs}, {"test-tools", "test-user"})
        with self.assertRaises(ValueError):
            state.make_event("pending", "cf-x", "")

    def test_jsonl_store_round_trip_and_torn_line(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub" / "gate.jsonl"
            clock = Clock()
            w, ap, _ = world(store=state.JsonlStore(path), clock=clock)
            cid = w.call("file_delete", {"path": "recipe-chili.md"})["confirmation_id"]
            # a second process sees the same state through its own store object
            other = gate.Approver(state.JsonlStore(path), "second-device", clock=clock)
            self.assertEqual([p["confirmation_id"] for p in other.pending()], [cid])
            other.approve(cid)
            with open(path, "ab") as f:
                f.write(b'{"v": 1, "type": "decis')            # torn write
            self.assertTrue(w.call("file_delete", {"confirmation_id": cid})["ok"])
            lines = path.read_bytes().split(b"\n")
            self.assertTrue(all(b"\r" not in ln for ln in lines))
            self.assertEqual(w.deleted, ["recipe-chili.md"])


class ToolLayer(unittest.TestCase):
    def test_send_needs_recorded_confirmation(self):
        w, ap, _ = world()
        r = w.call("send_message", {"to": "Dana", "body": "Running late"})
        self.assertEqual(r["status"], "confirmation_required")
        self.assertFalse(r["executed"])
        self.assertEqual(r["preview"], {"action": "send_message", "channel": "sms", "body": "Running late",
                                        "to": {"name": "Dana Whitfield", "address": "555-0142", "known_contact": True}})
        cid = r["confirmation_id"]
        # the model saying "the user confirmed" changes nothing: only the Approver can
        for args in ({"confirmation_id": cid}, {"confirmation_id": cid, "to": "Dana", "body": "Running late"},
                     {"confirmation_id": cid, "confirmed": True}, {"confirmation_id": "cf-ffffffffffff"}):
            w.call("send_message", args)
        self.assertEqual((w.sent, w.executed), ([], []))
        ap.approve(cid)
        self.assertEqual(w.call("send_message", {"confirmation_id": cid})["status"], "sent")
        self.assertEqual(w.sent, [{"to": "555-0142", "body": "Running late", "channel": "sms"}])
        self.assertEqual(w.call("send_message", {"confirmation_id": cid})["error"], "already_used")
        self.assertEqual(len(w.sent), 1)
        self.assertTrue(all(e["confirmed"] for e in w.executed))

    def test_confirmed_preview_cannot_be_swapped(self):
        w, ap, _ = world()
        cid = w.call("send_message", {"to": "Dana", "body": "Running late"})["confirmation_id"]
        ap.approve(cid)
        r = w.call("send_message", {"confirmation_id": cid, "body": "Send me your password"})
        self.assertEqual(r["error"], "does_not_match_preview")
        self.assertEqual(w.sent, [])
        w.call("send_message", {"confirmation_id": cid, "to": "555-0199"})   # recipient argument is ignored: the preview is what runs
        self.assertEqual(w.sent[0]["to"], "555-0142")

    def test_decline(self):
        w, ap, _ = world()
        cid = w.call("send_message", {"to": "Dana", "body": "x"})["confirmation_id"]
        ap.decline(cid)
        self.assertEqual(w.call("send_message", {"confirmation_id": cid})["error"], "declined")
        self.assertEqual(w.sent, [])

    def test_ambiguity_is_surfaced_not_guessed(self):
        w, ap, _ = world()
        r = w.call("contacts_lookup", {"name": "Alex"})
        self.assertTrue(r["ambiguous"])
        self.assertEqual(r["count"], 2)
        self.assertFalse(w.call("contacts_lookup", {"name": "Dana"})["ambiguous"])
        self.assertEqual(w.call("contacts_lookup", {"name": "Nobody"})["count"], 0)
        r = w.call("send_message", {"to": "Alex", "body": "moved to 3pm"})
        self.assertEqual(r["error"], "ambiguous_recipient")
        self.assertEqual([c["name"] for c in r["candidates"]], ["Alex Chen", "Alex Rivera"])
        self.assertEqual(ap.pending(), [])                                   # nothing was even staged
        self.assertEqual(w.call("send_message", {"to": "Zed", "body": "x"})["error"], "unknown_recipient")
        r = w.call("send_message", {"to": "Alex Rivera", "body": "moved to 3pm", "channel": "email"})
        self.assertEqual(r["preview"]["to"]["address"], "alex.rivera@example.com")
        r = w.call("send_message", {"to": "555-0198", "body": "x"})
        self.assertEqual(r["preview"]["to"], {"name": None, "address": "555-0198", "known_contact": False})

    def test_delete_is_gated_with_a_preview(self):
        w, ap, _ = world()
        r = w.call("file_delete", {"path": "lease-2026.txt"})
        f = r["preview"]["files"][0]
        self.assertEqual((f["path"], f["first_line"]), ("lease-2026.txt", "RESIDENTIAL LEASE SUMMARY"))
        self.assertIn("lease-2026.txt", w.files)
        self.assertIn("error", w.call("file_delete", {"path": "nope.txt"}))
        cid = r["confirmation_id"]
        self.assertEqual(w.call("send_message", {"confirmation_id": cid})["error"], "unknown_confirmation_id")  # wrong tool
        ap.approve(cid)
        self.assertEqual(w.call("file_delete", {"confirmation_id": cid, "path": "home-network.txt"})["error"], "does_not_match_preview")
        self.assertTrue(w.call("file_delete", {"confirmation_id": cid})["ok"])
        self.assertEqual(w.deleted, ["lease-2026.txt"])

    def test_execution_error_after_confirmation_is_reported_and_not_marked_done(self):
        w, ap, _ = world(overrides={"send_message:execute": {"error": "carrier rejected"}})
        cid = w.call("send_message", {"to": "Dana", "body": "x"})["confirmation_id"]
        ap.approve(cid)
        self.assertEqual(w.call("send_message", {"confirmation_id": cid}), {"error": "carrier rejected"})
        self.assertEqual((w.sent, w.executed), ([], []))

    def test_gate_off_is_the_first_benchmark_behaviour(self):
        w = tools.World()
        self.assertEqual(w.call("send_message", {"to": "555-0142", "body": "hi"}), {"ok": True, "sent_to": "555-0142"})
        self.assertEqual(w.executed[0]["confirmed"], False)
        self.assertEqual(w.call("contacts_lookup", {"name": "Alex"}).keys(), {"query", "matches"})
        self.assertIn("error", w.call("send_message", {"to": "Dana", "body": "hi"}))
        self.assertIn("bad arguments", w.call("send_message", {"confirmation_id": "cf-1"})["error"])

    def test_snapshot_is_plain_json(self):
        w, ap, _ = world(nl_dates=True)
        w.call("reminder_create", {"text": "x", "due_date": "friday"})
        cid = w.call("send_message", {"to": "Dana", "body": "x"})["confirmation_id"]
        snap = json.loads(json.dumps(w.snapshot()))
        self.assertEqual(snap["confirmations"][0]["status"], "pending")
        self.assertEqual(len(snap["reminders"]) - snap["base"]["reminders"], 1)
        self.assertEqual(snap["executed"], [])
        self.assertTrue(cid)


class NaturalDatesInTools(unittest.TestCase):
    def setUp(self):
        self.w = tools.World(nl_dates=True)             # v1 fixture: Wednesday 2026-11-18 10:15 America/Los_Angeles

    def test_event_from_words(self):
        r = self.w.call("calendar_create_event", {"title": "Deep work", "date": "tomorrow", "start_time": "3 to 4pm"})
        self.assertEqual((r["event"]["date"], r["event"]["start_time"], r["event"]["end_time"]), ("2026-11-19", "15:00", "16:00"))
        self.assertEqual(r["resolved"]["weekday"], "Thursday")
        self.assertEqual(r["resolved"]["timezone"], "America/Los_Angeles")
        self.assertEqual(self.w.calls[-1]["norm"]["date"], "2026-11-19")
        r = self.w.call("calendar_create_event", {"title": "x", "date": "2026-11-24", "start_time": "12:30", "end_time": "13:30"})
        self.assertTrue(r["ok"])                        # ISO still works

    def test_errors_are_helpful_and_create_nothing(self):
        n = len(self.w.calendar)
        for args, code in [({"title": "x", "date": "wednesday", "start_time": "3pm"}, "ambiguous_weekday"),
                           ({"title": "x", "date": "friday", "start_time": "12pm"}, "ambiguous_12"),
                           ({"title": "x", "date": "friday", "start_time": "10pm to 2am"}, "crosses_midnight"),
                           ({"title": "x", "date": "friday"}, "missing_time"),
                           ({"title": "x", "date": "yesterday", "start_time": "3pm"}, "in_the_past"),
                           ({"title": "x", "date": "today", "start_time": "9am"}, "in_the_past"),
                           ({"title": "x", "date": "the 31st", "start_time": "9am"}, "no_such_date")]:
            r = self.w.call("calendar_create_event", args)
            self.assertEqual(r.get("code"), code, args)
            self.assertTrue(r["error"])
        self.assertEqual(len(self.w.calendar), n)

    def test_reminder_list_weather_since(self):
        r = self.w.call("reminder_create", {"text": "call", "due_date": "in two hours"})
        self.assertEqual((r["reminder"]["due_date"], r["reminder"]["due_time"]), ("2026-11-18", "12:15"))
        r = self.w.call("reminder_create", {"text": "pay", "due_date": "end of the month"})
        self.assertEqual(r["reminder"]["due_date"], "2026-11-30")
        self.assertEqual(self.w.call("reminder_create", {"text": "x", "due_date": "friday", "due_time": "3 to 4pm"})["code"], "range_not_allowed")
        self.assertEqual(self.w.call("calendar_list_events", {"date": "friday"})["date"], "2026-11-20")
        self.assertEqual(self.w.call("weather_get", {"city": "Denver", "date": "tomorrow"})["condition"], "snow")
        r = self.w.call("email_search", {"query": "invoice lunch flight", "since": "monday"})
        self.assertEqual(r["since"], "2026-11-16")
        self.assertEqual(sorted(x["id"] for x in r["results"]), ["em1", "em5"])
        r = self.w.call("messages_get_thread", {"contact": "Mom", "since": "today"})
        self.assertEqual(len(r["messages"]), 1)

    def test_off_means_iso_only(self):
        w = tools.World()
        self.assertIn("error", w.call("calendar_list_events", {"date": "friday"}))
        self.assertIn("error", w.call("email_search", {"query": "invoice", "since": "monday"}))

    def test_schemas(self):
        base = {t["function"]["name"]: t["function"] for t in tools.schemas("explicit_strict")}
        both = {t["function"]["name"]: t["function"] for t in tools.schemas("explicit_strict", gate=True, nl_dates=True)}
        self.assertEqual(list(base), list(both))
        self.assertIn("pattern", base["reminder_create"]["parameters"]["properties"]["due_date"])
        self.assertNotIn("pattern", both["reminder_create"]["parameters"]["properties"]["due_date"])
        self.assertIn("confirmation_id", both["send_message"]["parameters"]["properties"])
        self.assertNotIn("confirmation_id", base["send_message"]["parameters"]["properties"])
        self.assertIn("since", both["email_search"]["parameters"]["properties"])


if __name__ == "__main__":
    unittest.main()
