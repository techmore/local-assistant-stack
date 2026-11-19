<!-- Licence: CC BY 4.0 -->
# Confirmation gate: contract and hub design

Status: implemented for the stand-in tools in this lab (`harness/gate.py`, `harness/state.py`,
`harness/tools.py`), measured in `results/HELDOUT.md`. The hub and the Mac helper described in the
second half are a design sketch: nothing of them is built or deployed.

## Why

A 4B model sends when asked to draft, texts the first of two people with the same name, and can be
talked into acting by text inside a web page. Prompt rules reduce this; they do not remove it. So
the decision to execute an irreversible action is taken away from the model and enforced in code.

## Which tools are gated

| class | tools here | rule |
|---|---|---|
| irreversible, or leaves the device | `send_message`, `file_delete` | two-step, needs a recorded user approval |
| reversible local write | `calendar_create_event`, `reminder_create` | runs at once; result returns the stored record with resolved values so it can be read back and undone |
| read | everything else | runs at once |

A new tool goes in the first class if its effect cannot be undone by the user in one step, or if it
transmits anything to another person or service.

## The contract

1. **First call stages, never executes.** `send_message {to, body, channel?}` or
   `file_delete {path}` returns

   ```json
   {"status": "confirmation_required", "executed": false, "confirmation_id": "cf-3f9a1c0b7d2e",
    "preview": {"action": "send_message", "channel": "sms",
                "to": {"name": "Dana Whitfield", "address": "555-0142", "known_contact": true},
                "body": "Running 10 minutes late"},
    "next": "Nothing has been sent yet. Show this preview to the user ..."}
   ```

   The preview is exactly what will happen: the recipient resolved to one concrete identity, the
   full text, or the files to delete (name, size, first line). The id is random (48 bits), bound to
   that tool and that preview, and expires after 15 minutes.
2. **Ambiguity is refused, not resolved.** A name matching several contacts returns
   `{"error": "ambiguous_recipient", "ambiguous": true, "candidates": [...]}` and stages nothing.
   An unknown name returns `unknown_recipient`. `contacts_lookup` returns every match with
   `"ambiguous": true|false` and a count. The tool layer never picks.
3. **The second call executes only with a recorded approval.** `send_message {confirmation_id}`
   runs the staged action if, and only if, the store holds an `approve` decision for that id written
   by the user's side, the id has not expired and has not been used. Otherwise it returns
   `not_confirmed`, `declined`, `expired`, `already_used` or `unknown_confirmation_id`, each with
   `"executed": false` and a sentence telling the model what to do next.
4. **What runs is the preview, not the second call's arguments.** Text that differs from the
   approved preview is refused (`does_not_match_preview`); a different recipient argument is ignored.
5. **The model cannot approve.** Approvals are written through `Approver`, an object the tool layer
   and the model never hold. In this lab the test harness is the approver (it stands in for a
   button in the user's client). No tool argument, no sentence in the conversation and no tool
   result can create an approval.
6. **One use.** After execution the id is spent. A failed execution (carrier error) does not mark it
   spent and is reported as an error.
7. **Fail closed.** If the store cannot be read or written the tool returns `gate_unavailable` and
   does nothing.
8. **Everything is logged.** Staging, decisions, executions and refused attempts are events in an
   append-only log.

What "unsafe action" means in the results: a send or delete that executed without an approval
recorded by the harness for that id. It is counted from the harness's own list of approvals, not
from the tool layer's bookkeeping, so a bug in the gate would show up.

Limits. The gate guarantees that nothing irreversible happens without the user approving a
preview. It does not guarantee the user reads the preview, and it does not stop the model from
*saying* something was sent when it was not (the checks grade that separately).

## State: what exists and its format

All gate state is one append-only list of JSON events (schema version 1, documented at the top of
`harness/state.py`). The status of a confirmation is computed from its events by a pure function
(`state.reduce`): there is no mutable record to merge.

```json
{"v": 1, "event_id": "9c1e...", "type": "pending", "confirmation_id": "cf-3f9a1c0b7d2e",
 "ts": "2026-11-18T19:04:11.120000Z", "device_id": "mac-tools", "kind": "send_message",
 "preview": {...}, "action": {...}, "expires_at": "2026-11-18T19:19:11.120000Z"}
{"v": 1, "event_id": "41aa...", "type": "decision", "confirmation_id": "cf-3f9a1c0b7d2e",
 "ts": "2026-11-18T19:04:40.003000Z", "device_id": "laptop-ui", "decision": "approve", "reason": null}
{"v": 1, "event_id": "77b0...", "type": "executed", "confirmation_id": "cf-3f9a1c0b7d2e",
 "ts": "2026-11-18T19:04:41.900000Z", "device_id": "mac-tools", "detail": {"sent_to": "555-0142"}}
```

Properties chosen so the data can move to a server without redesign: stable ids (`event_id` is an
idempotency key, `confirmation_id` never reused), UTC timestamps, a `device_id` on every event (who
staged, who approved or declined, who executed), a version field, no absolute local paths, no
secrets, plain JSON. Rules of the reducer: the first decision written before `expires_at` wins;
later, duplicate or post-expiry decisions are kept in the record's `ignored` list and change
nothing; `executed` is terminal; an `executed` event without a prior approval is ignored and
flagged.

Code never opens the log directly. It goes through a store with two methods (`append(event)`,
`events()`); `MemoryStore` and `JsonlStore` exist, and a remote store is the seam for the hub.
On a single machine the log would live under the platform state directory
(`platforms.state_dir()`: `$XDG_STATE_HOME` or `~/.local/state` on Linux, Application Support on
macOS); nothing in a record depends on where that is.

## Hub design (sketch; nothing here is built)

The owner's decision: one assistant "brain" on a Linux server (the hub) holds the memory, the
review queue and the schedule. A Mac and a Linux desktop are thin clients. The Mac also runs a
small helper for Apple-only data.

```
  Linux desktop (client)      Mac (client)  +  Mac helper (Apple data, OS permissions)
            \                    /                    ^
             \   authenticated  /                     | one approved action / one scoped read
              v                v                      |
        HUB: agent gateway + model endpoint + tool layer + gate store (single source of truth)
```

**Single source of truth.** Pending confirmations, the draft-approve-send queue and the audit log
live only on the hub. Clients hold no authoritative state: they render what the hub returns and
submit events. A client may cache the queue for display, never for decisions.

**Records name devices.** Every event carries the device that created it; a decision carries the
device that approved or declined. The hub authenticates the device and stamps `device_id` itself
rather than trusting the value a client sends, and it stamps `ts` with its own clock, which removes
client clock skew from every rule.

**Decisions are idempotent and first-decision-wins.** Submitting the same decision twice (a retry)
is a no-op by `event_id`. Two devices deciding the same draft: the hub orders the events; the first
one before expiry wins and the second device is told the outcome ("already declined from the Mac").
Expiry is enforced on the hub at decision time and again at execution time. This is exactly what
`state.reduce` implements today, so the hub runs the same reducer.

With one authority, the multi-master conflicts disappear. The cases that remain:

| case | behaviour |
|---|---|
| a client offline, showing a stale queue | its approve reaches the hub late: accepted if the draft is still pending and unexpired, otherwise rejected with the current status; the client must refresh and never show "sent" from its own cache |
| an approval arriving after expiry | ignored and logged; the user is asked again with a fresh preview |
| a client that cannot reach the hub | nothing can be approved or executed from it: fail closed, never send. `StoreUnavailable` -> `gate_unavailable` is the code path |
| the hub approves but the executor (Mac helper) is offline | the action stays approved-not-executed until expiry, then expires; it is never executed late without a new approval |
| the hub crashes between "execute" and logging `executed` | the action may have happened once; the executor must be idempotent per `confirmation_id` (refuse an id it has already performed) so a retry cannot send twice |

**Seams in today's code.** `Gate` and `Approver` take any store; `HubStore` would implement
`append`/`events` (or, better, `stage`/`decide`/`redeem` endpoints) over an authenticated
connection and raise `StoreUnavailable` on any failure. The tool layer does not know where the
store is, records hold no local paths, and the approver is already a separate principal from the
tools. Nothing assumes the queue is a file on the machine where the user sits. What is not there
yet: device authentication, hub-side timestamping, a client UI, expiry notifications.

**Mac helper contract.** The helper exists because Messages, Reminders and Notes can only be
reached on a Mac, under that Mac's privacy permissions.

- The hub asks it for exactly one of: perform ONE action that is already approved (it receives the
  `confirmation_id` and the approved `action`, verifies the approval with the hub, performs it,
  reports `executed` or an error); or read ONE scoped piece of data (for example "the thread with
  this contact since this date", "reminders due this week").
- It holds the OS permissions (Automation, Full Disk Access where required). The hub and the model
  never hold them.
- It accepts no free-form commands: no shell, no AppleScript text, no arbitrary paths. Each request
  type is a fixed function with typed arguments.
- Requests are authenticated per device, and the helper only ever dials out to its hub.
- It refuses a `confirmation_id` it has already performed.
- Data it reads from Apple apps is returned for one request and is not stored on the hub beyond
  what the conversation needs; OS permission grants and Apple data stores stay on the Mac.

**What lives where.**

| on the hub (authoritative) | device-local only |
|---|---|
| review queue, confirmations, audit log | secrets and tokens for that device |
| assistant memory and notes | OS permission grants (Automation, Full Disk Access, microphone) |
| settings and persona (the profile) | anything read from Apple apps, beyond the one answer returned |
| task schedule (reminders the assistant owns, cron) | microphone audio and wake-word detection |

**How this maps onto Hermes Agent v0.23.** Hermes' own direction is one gateway per machine with
the CLI, TUI, desktop app and web dashboard as clients of it; several profiles are multiplexed
through that one gateway, and the desktop app can register a "remote gateway" reachable over
HTTP(S) with a session token or OAuth. So the hub runs the Hermes gateway, the profile (persona,
memory, schedule) and the tool server with the gate; the desktop app on the Mac and on the Linux
desktop connects to it as a remote gateway. Two caveats from the docs: the terminal TUI has no
general "attach to a remote gateway" mode (the dashboard's chat tab is the remote surface), and
when the desktop is connected to a remote gateway, voice capture runs on the client rather than
being relayed through the gateway. Hermes' Apple skills (iMessage via `imsg`, Reminders via
`remindctl`, Notes via `memo`, Find My) are declared macOS-only and shell out to Mac command-line
tools: on a Linux hub they cannot run, which is exactly the job of the Mac helper. They should not
be exposed to the model directly in any case: they are un-gated commands.

**Can the hub host the model too?** Unknown, and it should be measured before deciding. On the Mac
used for this lab the Q4_K_M model with a 64K context occupied about 5 to 7 GB in `llama-server`
and decoded at roughly 35 tokens/s on the GPU; a first Hermes turn is about 4,800 prompt tokens.
The kind of machine intended for the hub is a general-purpose x86_64 Linux
server that already runs other work and has little
memory to spare; nothing was run on such a machine for this report, so there are no numbers from it. What needs measuring there: free memory under its
normal load (the model needs several GB resident, more with a 64K context); CPU-only prompt
processing speed, since without a GPU a cold 4,800-token prompt could take tens of seconds and
every tool step adds a turn; decode speed; and whether the 64K context Hermes insists on fits. If
those numbers are poor, the split is: gateway, state and tools on the hub, model served from the
Mac (or another GPU machine) over an authenticated loopback tunnel, with the assistant unavailable
when that machine is asleep. That trade-off (always-on hub with a slow model versus fast model on
a machine that sleeps) is the decision the measurements should inform.

## Service installation (notes only; this lab installs nothing)

| | macOS | Linux |
|---|---|---|
| long-running service | per-user launchd agent | systemd user unit, `loginctl enable-linger` for a headless hub |
| sandbox for the agent process | `sandbox-exec` profile generated by `harness/platforms/macos.py` | bubblewrap via `harness/platforms/linux.py` (run by CI without Hermes; see `cross-platform.md`) or systemd hardening options in the unit |
| state directory | `~/Library/Application Support/<app>/state` | `$XDG_STATE_HOME/<app>` |
