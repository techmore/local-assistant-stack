<!-- Licence: CC BY 4.0 -->
# Cross-platform status (macOS and Linux)

Target: the assistant runs on macOS and on Linux desktops (including Arch-based systems and
aarch64), with the state on a Linux server later. Everything below was developed and run on
macOS (Apple Silicon). **Nothing has been executed on Linux yet.** The unit tests are written to
be OS-independent and a CI workflow runs them on `ubuntu-latest` and `macos-latest`, but until
that workflow has run, Linux is unverified.

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
| sandbox for the agent process | `sandbox-exec`, profile generated at run time from the current home and lab paths (used for every run here) | bubblewrap wrapper, **untested**; network filtering is a known gap (see the module docstring). Requires `LAB_ALLOW_UNTESTED_SANDBOX=1` |
| no sandbox available | harness exits 78 and does not start the agent | same |
| state/config/data directories | `~/Library/Application Support/<app>/...` | `$XDG_STATE_HOME`, `$XDG_CONFIG_HOME`, `$XDG_DATA_HOME` with the usual fallbacks |
| service installation | notes only (launchd agent) | notes only (systemd user unit, linger) |
| notification hook | stub (returns False) | stub (returns False) |

## macOS-only today, and why

- The shell helpers in `scripts/` and `bin/` are bash and use `lsof`; they run on Linux in
  principle but were only run on macOS. `harness/runner.py` reads process memory with `ps -o rss=`,
  which exists on both.
- The evaluation sandbox profile (network allow-list, automation denial) is a macOS feature set;
  the Linux wrapper does not yet match it.
- Model serving was measured only with `llama-server` using Metal. On Linux the same GGUF files
  run on CPU, Vulkan or CUDA builds; speeds will differ and were not measured.

## Untested on Linux

Everything: unit tests, the harness against a model server, the bubblewrap wrapper, and Hermes
itself under that wrapper.

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
