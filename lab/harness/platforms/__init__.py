# SPDX-License-Identifier: MIT
"""Everything that differs per operating system lives behind this package.

    sandbox = platforms.get_sandbox()          # raises SandboxUnavailable: callers must NOT run unsandboxed
    argv = sandbox.wrap(argv, mode="eval", lab=lab_dir)
    platforms.state_dir("local-assistant")     # XDG on Linux, ~/Library/Application Support on macOS

Implementations: macos.py (sandbox-exec, used and tested in this lab) and linux.py
(bubblewrap; written from documentation, UNTESTED). Nothing outside this package may call
sandbox-exec, bwrap, launchctl, systemctl, osascript or other OS-specific commands.
"""
import os
import sys
from pathlib import Path


class SandboxUnavailable(RuntimeError):
    """No working sandbox wrapper on this system. The harness refuses to start Hermes."""


def system():
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return sys.platform


def get_sandbox():
    """Return the sandbox implementation for this OS, or raise SandboxUnavailable (fail closed)."""
    s = system()
    if s == "macos":
        from . import macos as impl
    elif s == "linux":
        from . import linux as impl
    else:
        raise SandboxUnavailable(f"no sandbox wrapper implemented for platform '{s}'")
    ok, why = impl.available()
    if not ok:
        raise SandboxUnavailable(why)
    return impl


def _home():
    return Path(os.environ.get("HOME") or Path.home())


def config_dir(app):
    """Settings and profile. Linux: $XDG_CONFIG_HOME or ~/.config; macOS: ~/Library/Application Support."""
    if system() == "macos":
        return _home() / "Library" / "Application Support" / app
    return Path(os.environ.get("XDG_CONFIG_HOME") or _home() / ".config") / app


def state_dir(app):
    """Queues, audit log, device id. Linux: $XDG_STATE_HOME or ~/.local/state; macOS: Application Support/<app>/state."""
    if system() == "macos":
        return _home() / "Library" / "Application Support" / app / "state"
    return Path(os.environ.get("XDG_STATE_HOME") or _home() / ".local" / "state") / app


def data_dir(app):
    """Larger user data. Linux: $XDG_DATA_HOME or ~/.local/share; macOS: Application Support/<app>/data."""
    if system() == "macos":
        return _home() / "Library" / "Application Support" / app / "data"
    return Path(os.environ.get("XDG_DATA_HOME") or _home() / ".local" / "share") / app


def service_notes():
    """How a long-running assistant service would be installed here. Text only: this lab installs nothing."""
    if system() == "macos":
        return ("macOS: a per-user launchd agent (a plist in the user's LaunchAgents folder, loaded with launchctl bootstrap). "
                "Not created by this lab.")
    if system() == "linux":
        return ("Linux: a systemd user unit (~/.config/systemd/user/<name>.service, enabled with systemctl --user enable --now; "
                "loginctl enable-linger to keep it running without a session). Not created by this lab.")
    return "no service notes for this platform"


def notify(title, body):
    """Notification hook (e.g. 'a draft is waiting for approval'). Not implemented: returns False so callers fall back to printing."""
    return False
