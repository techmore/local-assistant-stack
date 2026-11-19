# SPDX-License-Identifier: MIT
"""Linux sandbox: bubblewrap (bwrap).

Status. This wrapper was first written from the bubblewrap and systemd documentation on a Mac.
It is now executed by the `linux-sandbox` CI workflow (tests/test_linux_sandbox.py) on GitHub's
hosted Ubuntu runners; docs/design/cross-platform.md lists the runner images, kernel and bwrap
versions, what that job found and what it does not cover. Hermes itself has never been run under
this wrapper, and nothing here has been run on a desktop session or on an Arch-based system.

Modes (intended to match macOS):
  guard  the real filesystem read-write, EXCEPT read-only binds over the user's own Hermes
         install, PATH wrappers, systemd user units and shell profiles, and empty stand-ins over
         other agents' login stores. New PID/IPC/UTS namespaces, minimal /dev.
  eval   the whole filesystem read-only; an empty tmpfs over the home directory, /tmp, /run
         (session and system D-Bus sockets, container-engine sockets, /run/media) and /mnt,
         /media, /srv; the lab bound back in read-only with <lab>/hermes-home and <lab>/run
         read-write; HOME set to <lab>/run/sandbox-home (created by the wrapper); new
         PID/IPC/UTS namespaces; the process dies with its parent.

What CI verifies: both modes as described above, exit-code propagation, fail-closed behaviour
(no bwrap, bwrap that cannot create a sandbox, no opt-in, an unusable network setting), loopback
TCP from inside eval mode to a server outside it, and the lab's MCP tool server running inside
eval mode.

What is NOT enforced or not verified (differences from macOS):
  * Network. bwrap can only remove the network entirely (--unshare-net), which would also cut
    the loopback connection to the model server, so the network namespace stays shared: outbound
    connections to any address are possible, and so are abstract Unix sockets. CI asserts this
    gap so that it stays documented. With LAB_LINUX_NET=systemd the wrapper runs bwrap inside
    `systemd-run --user --scope -p IPAddressDeny=any -p IPAddressAllow=localhost`; available()
    then first checks that the filter really blocks a packet and refuses to run if it does not
    (a user manager usually may not attach the BPF filter, in which case systemd ignores the
    setting). See cross-platform.md for what the hosted runners did.
  * No per-port loopback deny list and no exec deny list (macOS eval mode has both).
  * guard mode can only protect profile files that exist when the sandbox starts: a missing
    ~/.zshrc can still be created. macOS denies by path.
  * In eval mode an interpreter installed under the home directory (pyenv, a default uv
    install) is hidden with the rest of the home directory; keep it inside the lab or system-wide.
  * Interactive terminal use (--new-session detaches the controlling terminal), GPU devices
    (--dev gives a minimal /dev), desktop sessions: not tested.
  * Unprivileged user namespaces must be usable by bwrap. Ubuntu 23.10+ restricts them through
    AppArmor (kernel.apparmor_restrict_unprivileged_userns=1); available() detects a bwrap that
    cannot create a sandbox and refuses.

Because Hermes has not been run under it and egress is unfiltered by default, the harness still
asks for LAB_ALLOW_UNTESTED_SANDBOX=1 before using this wrapper.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

NEEDS_OPT_IN = True

_NAMESPACES = ["--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc", "--unshare-uts"]
_KERNEL_FS = ["--proc", "/proc", "--dev", "/dev"]          # must come AFTER the bind of /, or that bind covers them
_NET_SCOPE = ["systemd-run", "--user", "--scope", "--quiet", "--collect", "-p", "IPAddressDeny=any",
              "-p", "IPAddressAllow=localhost", "--"]
# Sends one empty UDP datagram to a documentation-only address (RFC 5737). With the address filter
# in place the kernel refuses it (EPERM); exit 0 only in that case.
_NET_PROBE = ("import socket,sys\n"
              "s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)\n"
              "try:\n s.sendto(b'',('192.0.2.1',9))\n"
              "except PermissionError:\n sys.exit(0)\n"
              "except OSError:\n sys.exit(3)\n"
              "sys.exit(2)\n")


def _last_line(text):
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    return lines[-1][:200] if lines else "no error output"


def _probe_bwrap(exe):
    """Can bwrap build the kind of sandbox wrap() asks for? Cheap: runs `true` in one."""
    cmd = [exe] + _NAMESPACES + ["--ro-bind", "/", "/"] + _KERNEL_FS + ["--", shutil.which("true") or "/bin/true"]
    try:
        r = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"bubblewrap (bwrap) could not be run ({type(e).__name__}). Refusing to run Hermes unsandboxed."
    if r.returncode == 0:
        return True, ""
    return False, ("bubblewrap (bwrap) is installed but cannot create a sandbox here: \"" + _last_line(r.stderr) + "\". "
                   "The usual cause is that unprivileged user namespaces are restricted: on Ubuntu 23.10 and later by "
                   "AppArmor (sysctl kernel.apparmor_restrict_unprivileged_userns=1; allow them for bwrap with an AppArmor "
                   "profile that grants 'userns', or set the sysctl to 0), elsewhere by kernel.unprivileged_userns_clone=0 "
                   "or user.max_user_namespaces=0, or by an enclosing container. See docs/design/cross-platform.md. "
                   "Refusing to run Hermes unsandboxed.")


def _probe_net_filter():
    """Does the systemd scope really filter egress? Fail closed when it cannot be shown to."""
    refuse = " Unset LAB_LINUX_NET to run with the network unfiltered (see the module docstring), or fix the cause."
    try:
        r = subprocess.run(_NET_SCOPE + [sys.executable or "python3", "-c", _NET_PROBE],
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"LAB_LINUX_NET=systemd: the systemd scope could not be started ({type(e).__name__})." + refuse
    if r.returncode == 0:
        return True, ""
    if r.returncode == 2:
        return False, ("LAB_LINUX_NET=systemd: the scope started but IPAddressDeny was NOT enforced (a test packet to a "
                       "non-loopback address was accepted). A systemd user manager usually may not attach the BPF "
                       "address filter and then ignores the setting." + refuse)
    if r.returncode == 3:
        return False, ("LAB_LINUX_NET=systemd: could not tell whether IPAddressDeny is enforced (the test packet failed "
                       "for another reason, e.g. no route)." + refuse)
    return False, ("LAB_LINUX_NET=systemd: the systemd scope could not be started: \"" + _last_line(r.stderr) + "\"." + refuse)


def available():
    exe = shutil.which("bwrap")
    if not exe:
        return False, "bubblewrap (bwrap) not found: install it; this harness will not run Hermes unsandboxed"
    ok, why = _probe_bwrap(exe)
    if not ok:
        return False, why
    net = os.environ.get("LAB_LINUX_NET", "")
    if net not in ("", "systemd"):
        return False, f"LAB_LINUX_NET has an unknown value '{net}' (use 'systemd' or leave it unset). Refusing to run."
    if net == "systemd":
        ok, why = _probe_net_filter()
        if not ok:
            return False, why
    if NEEDS_OPT_IN and os.environ.get("LAB_ALLOW_UNTESTED_SANDBOX") != "1":
        return False, ("the Linux bubblewrap wrapper in harness/platforms/linux.py is exercised by CI on hosted Ubuntu "
                       "runners only: Hermes has not been run under it and it does not filter outbound network traffic "
                       "by default (docs/design/cross-platform.md). Review it for this machine, then set "
                       "LAB_ALLOW_UNTESTED_SANDBOX=1 to use it. Refusing to run Hermes unsandboxed.")
    return True, ""


def prepare(mode, lab, home=None):
    return None  # nothing to generate: the policy is the argv built by wrap()


def wrap(argv, mode, lab, home=None, refresh=False):
    home = Path(home or Path.home())
    lab = Path(lab)
    xdg_cfg = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    b = ["bwrap"] + _NAMESPACES
    if mode == "guard":
        b += ["--bind", "/", "/"] + _KERNEL_FS
        for p in (home / ".hermes", home / ".local" / "bin", xdg_cfg / "systemd" / "user", home / ".zshrc", home / ".zprofile",
                  home / ".zshenv", home / ".bashrc", home / ".bash_profile", home / ".profile"):
            if p.exists():
                b += ["--ro-bind", str(p), str(p)]
        for p in (home / ".codex", home / ".claude"):
            if p.is_dir():
                b += ["--tmpfs", str(p)]
        if (home / ".claude.json").is_file():
            b += ["--ro-bind", "/dev/null", str(home / ".claude.json")]
    elif mode == "eval":
        b += ["--ro-bind", "/", "/"] + _KERNEL_FS + ["--tmpfs", str(home), "--tmpfs", "/tmp"]
        # /run holds the session bus (/run/user), the system bus, container-engine sockets and, on
        # some distributions, removable media. All tmpfs mounts come before the lab binds so that a
        # lab living under one of these directories is not hidden again.
        for extra in ("/run", "/mnt", "/media", "/srv"):
            if Path(extra).is_dir():
                b += ["--tmpfs", extra]
        sandbox_home = lab / "run" / "sandbox-home"
        b += ["--ro-bind", str(lab), str(lab),
              "--bind", str(lab / "hermes-home"), str(lab / "hermes-home"),
              "--bind", str(lab / "run"), str(lab / "run"),
              "--dir", str(sandbox_home),
              "--setenv", "HOME", str(sandbox_home), "--chdir", str(lab / "run")]
    else:
        raise ValueError(f"unknown sandbox mode '{mode}'")
    if os.environ.get("LAB_LINUX_NET") == "systemd" and mode == "eval":
        b = _NET_SCOPE + b
    return b + ["--"] + list(argv)
