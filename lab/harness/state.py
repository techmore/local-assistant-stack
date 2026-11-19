# SPDX-License-Identifier: MIT
"""State for the confirmation gate: an append-only event log behind a small interface.

Everything the gate knows is a list of immutable EVENTS. The current status of a
confirmation is a pure function of its events (`reduce`). That choice is deliberate:

  * append-only data is easy to move to one authoritative place later (a hub): a client
    only ever submits an event and reads back the reduced status;
  * first-decision-wins and expiry are rules of the reducer, not of whoever writes;
  * the log doubles as the audit trail.

The tool layer and the approver are different principals. The tool layer may append
`pending`, `executed`, `failed` and `refused`; only an approver (the user's UI, here the test
harness) may append `decision`. Stores:

  MemoryStore   in-process list (unit tests, the raw-endpoint harness)
  JsonlStore    one JSON object per line in a file (the Hermes-level harness, where the
                tool server and the approver are different processes)
  a hub store   NOT implemented here: anything with `append` and `events` works, for
                example an HTTP client talking to the hub. If it cannot reach the hub it
                must raise StoreUnavailable; the gate then refuses to act (fail closed).

Event schema, version 1 (every field JSON; no absolute local paths; times are UTC):

  v                1
  event_id         uuid4 hex, unique per event (idempotency key for a hub)
  type             "pending" | "decision" | "executed" | "refused" | "failed"
                   ("failed": the approved action was attempted and did not happen; terminal, so the
                   same approval cannot be used for a blind retry. Readers that predate it ignore it.)
  confirmation_id  the id the events belong to ("cf-" + 12 hex)
  ts               "2026-11-18T19:04:11.123456Z"
  device_id        the device/client that wrote this event
  --- pending only
  kind             "send_message" | "file_delete" | ...
  preview          exactly what will happen (see docs/design/confirmation-gate.md)
  action           the arguments the executor will use (same content as the preview)
  expires_at       UTC timestamp after which it can no longer be approved or executed
  --- decision only
  decision         "approve" | "decline"
  reason           optional free text
  --- executed / refused
  detail           optional object (result summary, or why an attempt was refused)
"""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


class StoreUnavailable(RuntimeError):
    """The authoritative store cannot be reached. Callers must fail closed."""


def utc_now():
    return datetime.now(timezone.utc)


def ts(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def parse_ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)


def make_event(type_, confirmation_id, device_id, now=None, **fields):
    if not device_id:
        raise ValueError("every event needs a device_id")
    ev = {"v": SCHEMA_VERSION, "event_id": uuid.uuid4().hex, "type": type_, "confirmation_id": confirmation_id,
          "ts": ts(now or utc_now()), "device_id": device_id}
    ev.update(fields)
    return ev


class MemoryStore:
    def __init__(self):
        self._events = []

    def append(self, event):
        self._events.append(json.loads(json.dumps(event)))  # must be plain JSON

    def events(self):
        return list(self._events)


class JsonlStore:
    """One event per line. Appends are single short writes in O_APPEND mode; readers skip a torn last line."""

    def __init__(self, path):
        self.path = Path(path)

    def append(self, event):
        line = json.dumps(event, sort_keys=True, ensure_ascii=True) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(self.path), os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)

    def events(self):
        if not self.path.exists():
            return []
        out = []
        with open(self.path, "r", encoding="utf-8", newline="\n") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue  # torn write in progress
        return out


def reduce(events, now=None):
    """Event list -> {confirmation_id: record}. Pure; the same rules a hub would enforce.

    record: kind, preview, action, created_at, expires_at, created_by, status, decided_by,
            decided_at, executed_at, ignored (events that lost: late or duplicate decisions)
    status: pending | approved | declined | executed | failed | expired
    Rules: the FIRST decision written before expires_at wins; later or post-expiry decisions are
    kept in `ignored` and change nothing. `executed` is terminal. A pending or approved record
    whose expires_at has passed reads as expired.
    """
    now = now or utc_now()
    recs = {}
    for ev in events:
        if ev.get("v") != SCHEMA_VERSION:
            continue
        cid, typ = ev.get("confirmation_id"), ev.get("type")
        if typ == "pending":
            if cid in recs:
                continue  # ids are never reused; a duplicate pending is ignored
            recs[cid] = {"confirmation_id": cid, "kind": ev["kind"], "preview": ev["preview"], "action": ev["action"],
                         "created_at": ev["ts"], "expires_at": ev["expires_at"], "created_by": ev["device_id"],
                         "status": "pending", "decided_by": None, "decided_at": None, "executed_at": None, "ignored": []}
            continue
        r = recs.get(cid)
        if r is None:
            continue
        if typ == "decision":
            late = parse_ts(ev["ts"]) > parse_ts(r["expires_at"])
            if r["status"] != "pending" or r["decided_at"] or late or ev.get("decision") not in ("approve", "decline"):
                r["ignored"].append({"event_id": ev["event_id"], "why": "after_expiry" if late else "already_decided"})
                continue
            r["status"] = "approved" if ev["decision"] == "approve" else "declined"
            r["decided_by"], r["decided_at"] = ev["device_id"], ev["ts"]
        elif typ == "executed":
            if r["status"] == "approved":
                r["status"], r["executed_at"] = "executed", ev["ts"]
            else:
                r["ignored"].append({"event_id": ev["event_id"], "why": "executed_without_approval"})
        elif typ == "failed":
            if r["status"] == "approved":
                r["status"], r["failed_at"] = "failed", ev["ts"]
            else:
                r["ignored"].append({"event_id": ev["event_id"], "why": "failed_without_approval"})
    for r in recs.values():
        if r["status"] in ("pending", "approved") and now > parse_ts(r["expires_at"]):
            r["status"] = "expired"
    return recs
