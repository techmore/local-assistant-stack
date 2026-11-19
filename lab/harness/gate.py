# SPDX-License-Identifier: MIT
"""Confirmation gate for side-effecting tools. Enforced in code, outside the model.

    gate = Gate(store, device_id="laptop-tools")
    r = gate.stage("send_message", preview, action)      # nothing happens; returns confirmation_id
    ...the user is shown r["preview"] by the client and answers...
    Approver(store, device_id="laptop-ui").approve(cid)   # ONLY the user's client does this
    ok, rec_or_error = gate.redeem(cid, "send_message")   # tool's second call; True at most once

The model can call stage and redeem as often as it likes: redeem succeeds only if the store
holds an approval written by an Approver for that id, the id is unexpired and unused.
The gate never executes anything itself; the tool executes after redeem() returns True and
then the gate records `executed`. Contract: docs/design/confirmation-gate.md.
"""
import secrets
from datetime import timedelta

import state

DEFAULT_TTL_S = 15 * 60


class Gate:
    """Tool-side API. Cannot approve."""

    def __init__(self, store, device_id, ttl_s=DEFAULT_TTL_S, clock=state.utc_now, id_factory=None):
        self.store, self.device_id, self.ttl_s, self.clock = store, device_id, ttl_s, clock
        self._new_id = id_factory or (lambda: "cf-" + secrets.token_hex(6))

    def _records(self):
        try:
            return state.reduce(self.store.events(), self.clock())
        except state.StoreUnavailable:
            raise
        except Exception as e:  # an unreadable store is an unavailable store
            raise state.StoreUnavailable(str(e))

    def stage(self, kind, preview, action):
        """Record a pending confirmation. Staging the identical action again returns the open one."""
        for r in self._records().values():
            if r["status"] == "pending" and r["kind"] == kind and r["action"] == action:
                return r
        now = self.clock()
        cid = self._new_id()
        self.store.append(state.make_event("pending", cid, self.device_id, now, kind=kind, preview=preview, action=action,
                                           expires_at=state.ts(now + timedelta(seconds=self.ttl_s))))
        return self._records()[cid]

    def get(self, cid):
        return self._records().get(cid)

    def open(self):
        return [r for r in self._records().values() if r["status"] == "pending"]

    def redeem(self, cid, kind):
        """-> (True, record) exactly once per approved id, else (False, {"error": code, "message": text}).

        The caller must perform the action from record["action"] (not from model-supplied arguments)
        and then call executed(cid).
        """
        try:
            r = self._records().get(cid)
        except state.StoreUnavailable:
            return False, {"error": "gate_unavailable", "message": "The approval service cannot be reached, so nothing was done. Tell the user."}
        if r is None or r["kind"] != kind:
            return self._refuse(cid, "unknown_confirmation_id", "There is no such confirmation id for this tool. Nothing was done. "
                                "Call the tool without confirmation_id to prepare a new preview.")
        s = r["status"]
        if s == "approved":
            return True, r
        msg = {
            "pending": ("not_confirmed", "The user has NOT confirmed this yet, so nothing was done. Show the preview to the user, "
                                         "ask them to confirm, and stop. Call again only after the user says yes."),
            "declined": ("declined", "The user declined this. Nothing was done. Do not try again; tell the user it was cancelled."),
            "executed": ("already_used", "This confirmation id was already used once. Nothing more was done."),
            "expired": ("expired", "This confirmation expired. Nothing was done. Prepare a new preview and ask the user again."),
        }[s]
        return self._refuse(cid, *msg)

    def _refuse(self, cid, code, message):
        try:
            self.store.append(state.make_event("refused", cid, self.device_id, self.clock(), detail={"error": code}))
        except Exception:
            pass
        return False, {"error": code, "message": message}

    def executed(self, cid, detail=None):
        self.store.append(state.make_event("executed", cid, self.device_id, self.clock(), detail=detail or {}))


class Approver:
    """User-side API: the only code path that writes decisions. Never handed to the model or the tools."""

    def __init__(self, store, device_id, clock=state.utc_now):
        self.store, self.device_id, self.clock = store, device_id, clock

    def pending(self):
        return [r for r in state.reduce(self.store.events(), self.clock()).values() if r["status"] == "pending"]

    def _decide(self, cid, decision, reason=None):
        self.store.append(state.make_event("decision", cid, self.device_id, self.clock(), decision=decision, reason=reason))
        return state.reduce(self.store.events(), self.clock()).get(cid)

    def approve(self, cid):
        return self._decide(cid, "approve")

    def decline(self, cid, reason=None):
        return self._decide(cid, "decline", reason)
