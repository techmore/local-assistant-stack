<!-- Licence: CC BY 4.0 -->
# Cross-platform status (macOS and Linux)

Target: the assistant runs on macOS and on Linux desktops (including Arch-based systems and
aarch64), with the state on a Linux server later. Everything below was developed on macOS (Apple
Silicon), and every model and Hermes run was made there. On Linux, two CI workflows run on
GitHub-hosted Ubuntu runners: `unit-tests` (the pure-code tests) and `linux-sandbox` (the Linux
platform module, the bubblewrap wrapper and the shell helpers, executed for real). **No model
server and no Hermes process has been run on Linux.** The section
[Verified on Linux by CI](#verified-on-linux-by-ci) says exactly what was run and what was seen.

## Platform-neutral (Python standard library, `pathlib`, `zoneinfo`)

| part | files |
|---|---|
| date/time resolver | `harness/dates.py` (no system clock, locale or `TZ`; weekday and month names are tables, not `strftime`) |
| confirmation gate and its event log | `harness/gate.py`, `harness/state.py` |
| stand-in tools, fixtures, task sets, checks, simulated user | `harness/tools.py`, `harness/tasks*.py`, `harness/usersim.py`, `fixtures*/` |
| runner, proxy, MCP tool server, reports | `harness/runner.py`, `proxy.py`, `mcp_server.py`, `report*.py` (the runner needs `requests` only to talk to a model server) |
| persona package | `profiles/pocket-assistant/` |

A unit test (`test_library_code_has_no_os_specific_commands_or_paths`) fails if any module outside
`harness/platforms/` mentions an OS-specific command or an absolute home path.

Needs `tzdata` on systems without a system zoneinfo database (minimal containers, Windows):
`pip install tzdata`.

## Behind the platform interface (`harness/platforms/`)

| concern | macOS | Linux |
|---|---|---|
| sandbox for the agent process | `sandbox-exec`, profile generated at run time from the current home and lab paths (used for every run here) | bubblewrap wrapper, run by CI without Hermes (see below); outbound network is not filtered; opt-in with `LAB_ALLOW_UNTESTED_SANDBOX=1` |
| no sandbox available | harness exits 78 and does not start the agent | same; also when `bwrap` is installed but cannot create a sandbox, and when `LAB_LINUX_NET` asks for a filter that is not enforced |
| state/config/data directories | `~/Library/Application Support/<app>/...` | `$XDG_STATE_HOME`, `$XDG_CONFIG_HOME`, `$XDG_DATA_HOME` with the usual fallbacks |
| service installation | notes only (launchd agent) | notes only (systemd user unit, linger) |
| notification hook | stub (returns False) | stub (returns False) |

## macOS-only today, and why

- The shell helpers in `scripts/` and `bin/` are bash and use `lsof` (the serve scripts treat a
  port as free when `lsof` is missing, so install it). On Linux CI runs `bin/guard`,
  `scripts/serve_proxy.sh` and `scripts/stop_servers.sh`; `scripts/serve_llama.sh` and `bin/hermes`
  were only run on macOS. `harness/runner.py` reads process memory with `ps -o rss=`, which exists
  on both; the runner itself was not run on Linux.
- The evaluation sandbox profile (network allow-list, per-port loopback deny list, exec deny list,
  automation denial) is a macOS feature set; the Linux wrapper does not match it (see
  [Not enforced on Linux](#not-enforced-on-linux)).
- Model serving was measured only with `llama-server` using Metal. On Linux the same GGUF files
  run on CPU, Vulkan or CUDA builds; speeds will differ and were not measured.

## Verified on Linux by CI

Workflow `.github/workflows/linux-sandbox.yml`, test file `tests/test_linux_sandbox.py`. Each job
installs `bubblewrap` if the image lacks it, prints its versions, and runs all unit tests with
`LAB_REQUIRE_LINUX_SANDBOX=1`, which turns "the sandbox is not usable" from a skip into a failure.
128 tests are discovered; on these runners 126 run and 2 skip (both explained below). There is no
model and no Hermes in these jobs.

Runners used (GitHub-hosted, images of 2026-11-11; each with Python 3.11.18 and 3.14.10):

| runner label | image | OS | kernel | bwrap | systemd | user namespaces for bwrap |
|---|---|---|---|---|---|---|
| `ubuntu-latest` | ubuntu26 20261111.196.1 | Ubuntu 26.04.1 LTS | 7.0.0-1019-azure x86_64 | 0.11.1 | 259 | work as shipped: `kernel.apparmor_restrict_unprivileged_userns=1`, and the image has an AppArmor profile `bwrap-userns-restrict` |
| `ubuntu-24.04` | ubuntu24 20261111.370.1 | Ubuntu 24.04.5 LTS | 7.0.0-1017-azure x86_64 | 0.9.0 | 255 | **blocked as shipped** (sysctl is 1, no bwrap profile): `bwrap: setting up uid map: Permission denied`. The job loads an AppArmor profile that grants `userns` to the bwrap binary only |
| `ubuntu-24.04-arm` | ubuntu24-arm64 20261111.182.1 | Ubuntu 24.04.5 LTS | 7.0.0-1017-azure aarch64 | 0.9.0 | 255 | as `ubuntu-24.04` |
| `ubuntu-22.04` | ubuntu22 20261111.360.2 | Ubuntu 22.04.5 LTS | 6.8.0-1070-azure x86_64 | 0.6.1 | 249 | work as shipped (sysctl is 0) |

What the job runs and checks:

- **Platform interface**: `platforms.system()` is `linux`; `config_dir`, `state_dir`, `data_dir`
  with the XDG variables set, unset, and with `HOME` unset too; `service_notes()`.
- **Fail closed**: with no `bwrap` on `PATH`, without `LAB_ALLOW_UNTESTED_SANDBOX=1`, and with an
  unknown `LAB_LINUX_NET` value, `available()` returns a reason, `get_sandbox()` raises
  `SandboxUnavailable`, and `sandbox_exec.py` exits 78 in both modes without running the command
  (the command would have written a file; the file is absent).
- **Restricted user namespaces**: on the 24.04 images as shipped, and on 22.04 after the job sets
  `kernel.apparmor_restrict_unprivileged_userns=1` (there bwrap fails with `Creating new namespace
  failed: Permission denied`), `available()` reports that bwrap cannot create a sandbox, quotes
  bwrap's error, names the sysctl, and `sandbox_exec.py` exits 78 without running the command. On
  the 26.04 image this state could not be produced, because the image's own profile keeps bwrap
  working; the job says so and does not run that test there. A second test covers the same code
  path everywhere (macOS included) with a stand-in `bwrap` that fails.
- **Eval mode**, through `sandbox_exec.py --mode eval` on a temporary copy of the lab placed in
  the runner's real home directory: exit codes and output pass through; a marker file written to
  the home directory beforehand is not visible and the home directory lists only the path to the
  lab; writes to `<lab>/harness`, `/etc`, `/usr`, `/var/tmp` and `/` fail; writes to `<lab>/run`
  and `<lab>/hermes-home` succeed and are visible outside; `/tmp` is empty inside and a file
  written there does not appear outside; `HOME` is `<lab>/run/sandbox-home`, exists and is
  writable; the working directory is `<lab>/run`; the shell is PID 2 and sees 4 processes (about
  160 outside); `/run` is empty inside while outside it held the session bus socket, the system
  bus socket and the Docker socket; `/mnt`, `/media`, `/srv` are empty; a lab without `run/` is
  refused by bwrap and the command does not run; when the parent process is killed the sandboxed
  process stops. The same works with the lab under `/tmp`.
- **Loopback networking in eval mode**: an HTTP server on 127.0.0.1 outside the sandbox is fetched
  from inside (the way the model server is reached).
- **The MCP tool server inside eval mode**: `harness/mcp_server.py` answers `initialize`,
  `tools/list`, `tools/call` (`reminder_list`) and an unknown method over stdio, and writes
  `run/mcp_calls.jsonl` and `run/mcp_world.json`; with the gate on, a `send_message` call returns a
  confirmation id and appends one `pending` event to `run/gate_events.jsonl`.
- **Guard mode**, with a temporary directory as `HOME`: `~/.hermes`, `~/.local/bin`,
  `~/.config/systemd/user`, `~/.bashrc`, `~/.profile`, `~/.zshrc` can be read but not changed,
  removed or renamed; `~/.claude` and `~/.codex` list as empty, `~/.claude.json` reads as empty,
  and writes there do not reach the real files; other files in the home directory and the lab
  stay writable; new PID namespace.
- **Shell helpers**: `bash -n` and `shellcheck -S warning` on `bin/guard`, `bin/hermes`,
  `scripts/*.sh`, `hermes-env.sh` (shellcheck 0.8.0, 0.9.0 and 0.11.0); `scripts/stop_servers.sh`
  with nothing running, and with a live and a stale pid file; `scripts/serve_proxy.sh` starts the
  proxy on 127.0.0.1:18432, a second start reports the port busy, `stop_servers.sh` stops it;
  `bin/guard` with a venv created by the test runs a command, passes its exit code and
  `HERMES_HOME`, and exits 78 without the opt-in.

### What the job found, and what was changed

The wrapper had never been executed. Run unchanged against these tests (on the 26.04 image), the
original `linux.py` failed as follows; each item is fixed in `harness/platforms/linux.py`.

| found | fix |
|---|---|
| Both modes showed the host's process list (179 processes) although the PID namespace was new: `--proc /proc --dev /dev` came before the bind of `/`, which then covered them. | `/` is bound first, then `/proc` and `/dev`. |
| Eval mode set `HOME` to `<lab>/run/sandbox-home`, which nothing created. | The wrapper creates it (`--dir`). |
| Eval mode hid `/run/user` only. The rest of `/run` stayed visible, including the system D-Bus socket and the Docker socket. | Eval mode mounts an empty tmpfs over `/run`. |
| `LAB_LINUX_NET=systemd` started the scope, but `IPAddressDeny=any` was not enforced: a connection to a non-loopback address succeeded. The systemd user manager on these runners does not apply the filter and does not fail. | `available()` now sends one test packet from inside such a scope and refuses to run (exit 78) unless the kernel rejects it. Any other value of `LAB_LINUX_NET` than `systemd` is refused instead of being ignored. |
| Guard mode left `~/.claude.json` readable (macOS denies it). | It is replaced by an empty stand-in. |
| On Ubuntu 24.04 as shipped `bwrap` cannot create user namespaces; `available()` still said the sandbox was usable and the failure surfaced later as a bare bwrap error. | `available()` runs `true` in a sandbox first and returns the reason and the remedy. |
| The tmpfs mounts over `/mnt`, `/media`, `/srv` came after the lab binds, so a lab under one of them would have been hidden. Found by reading; not reproduced on a runner. | All tmpfs mounts come before the lab binds (checked on the generated arguments; a lab under `/tmp` is run for real). |
| shellcheck warnings in `bin/hermes` (an unchecked `cd`), `scripts/serve_llama.sh` and `scripts/stop_servers.sh` (unused loop variables). | Fixed. |

`harness/sandbox_exec.py` needed no change.

### Enabling bubblewrap on Ubuntu 24.04

Ubuntu 23.10 and later set `kernel.apparmor_restrict_unprivileged_userns=1`. On the 24.04 runner
images no AppArmor profile covers `bwrap`, so it fails with `setting up uid map: Permission
denied` and the harness refuses to run. The CI job uses the narrower of the two documented
remedies, a profile for the bwrap binary only:

```
abi <abi/4.0>,
include <tunables/global>
profile lab-ci-bwrap /usr/bin/bwrap flags=(unconfined) {
  userns,
}
```

saved under `/etc/apparmor.d/` and loaded with `sudo apparmor_parser -r <file>`. The alternative,
`sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0`, lifts the restriction for every
program; the job falls back to it only if the profile does not help, which did not happen.
Ubuntu 26.04 needed neither.

### Not enforced on Linux

Tests pin the first two so that this list stays true.

- **Outbound network.** Eval mode shares the host's network namespace, because the model server
  is reached over loopback. From inside the sandbox a TCP connection to the runner's own
  non-loopback address succeeded. Abstract Unix sockets are reachable for the same reason. The
  macOS profile allows loopback only. `LAB_LINUX_NET=systemd` did not provide filtering on any of
  the four runner images (see the table above); it is refused there rather than run unfiltered.
  Whether it works on a machine where the user manager may attach the filter is untested.
- **Profile files that do not exist yet.** Guard mode binds existing files read-only; a
  `~/.zprofile` that was absent when the sandbox started could be created inside it.
- No per-port loopback deny list and no exec deny list in eval mode.
- The environment is passed through unchanged apart from `HOME`.

### Still untested on Linux

- Hermes Agent under the wrapper, in either mode, and `bin/hermes`.
- A model server on Linux, `scripts/serve_llama.sh`, `harness/runner.py` against a server, and
  therefore every measured result.
- Arch-based systems, and any distribution other than Ubuntu 22.04, 24.04 and 26.04.
- aarch64 beyond the hosted `ubuntu-24.04-arm` runner (a virtual machine): no Apple Silicon or
  other ARM hardware, no model or Hermes there.
- Desktop sessions: a real login session with a display server, session D-Bus services, an
  interactive terminal (`--new-session` detaches the controlling terminal), GPU devices (the
  sandbox has a minimal `/dev`).
- Interpreters installed under the home directory (pyenv, a default `uv` install): eval mode
  hides them with the rest of the home directory. On the runners Python is outside it. The lab's
  `hermes-env.sh` keeps `uv` Pythons inside the lab.
- A working `LAB_LINUX_NET=systemd`.

## Hermes Agent v0.23.2: platform notes from its documentation

(From reading the documentation shipped in the release; not from running it on Linux.)

- **Core CLI and gateway**: macOS on Apple Silicon and Linux (x86_64 and aarch64, glibc + systemd)
  are both first-tier. Installs from the AUR, Homebrew and PyPI are listed as unsupported; on an
  Arch-based system the supported route is the project's install script. The gateway installs as a
  launchd agent on macOS and a systemd user service on Linux.
- **Desktop app**: documented for macOS (Apple Silicon), Windows and Linux, but Linux desktop
  packaging is disabled in the release workflow (local AppImage builds exist). On Linux the tray
  needs a StatusNotifier host, and under native Wayland the floating composer can only be resized
  from two edges because the compositor positions windows. A tiling Wayland compositor is therefore
  the least-tested surface.
- **Remote use**: the desktop app can register a remote gateway over HTTP(S) with a session token
  or OAuth. The terminal TUI has no general remote-attach mode.
- **Voice mode**: needs PortAudio, ffmpeg and Opus (Homebrew packages on macOS, distribution
  packages on Linux). Local Faster-Whisper is excluded on Intel macOS and Windows ARM64. With a
  remote gateway, the desktop app captures and plays audio on the client.
- **Wake word**: openWakeWord wheels target Apple Silicon with macOS 15 or later, Linux with glibc
  2.35 or later, and Windows x64; elsewhere the sherpa engine is used. The detector is on-device,
  one microphone, one listening surface at a time; on macOS microphone permission is granted per
  process.
- **Apple skills** (iMessage, Reminders, Notes, Find My): declared `Platforms: macos` and
  implemented by calling Mac command-line tools. They cannot run on a Linux hub. In this project's
  design they belong behind the Mac helper, not in the model's toolset.
