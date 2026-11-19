# SPDX-License-Identifier: MIT
"""Linux sandbox: bubblewrap (bwrap). UNTESTED: written from the bubblewrap and systemd
documentation on a Mac; it has never been executed. Treat it as a starting point and review
it on the target machine (Arch/Omarchy, Ubuntu) before trusting it.

Intended to match the macOS modes:
  guard  the real filesystem read-write, EXCEPT read-only binds over the user's own Hermes
         install, PATH wrappers, systemd user units and shell profiles, and empty tmpfs over
         other agents' login stores
  eval   the whole filesystem read-only, an empty tmpfs over the home directory with only the
         lab bound back in (read-only) and <lab>/hermes-home plus <lab>/run read-write, private
         /tmp, new PID/IPC/UTS namespaces, the process dies with its parent

Known gaps compared with macOS (must be closed before relying on it):
  * Network. bwrap can only remove the network entirely (--unshare-net), which would also cut
    the loopback connection to the model server. Unless LAB_LINUX_NET=systemd is set this
    wrapper therefore leaves the network namespace shared. With LAB_LINUX_NET=systemd it runs
    bwrap inside `systemd-run --user --scope -p IPAddressDeny=any -p IPAddressAllow=localhost`,
    which needs cgroup v2 with BPF address filtering available to the user manager.
  * There is no Apple Events equivalent to deny; D-Bus is the analogous channel. In eval mode
    the session bus socket is hidden because the home directory and /run/user are replaced.
  * Unprivileged user namespaces must be enabled (they are by default on Arch and Ubuntu;
    some hardened kernels and AppArmor profiles on Ubuntu 24.04+ restrict them).
Because it is untested, the harness asks for LAB_ALLOW_UNTESTED_SANDBOX=1 before using it.
"""
import os
import shutil
from pathlib import Path

UNTESTED = True


def available():
    if not shutil.which("bwrap"):
        return False, "bubblewrap (bwrap) not found: install it; this harness will not run Hermes unsandboxed"
    if UNTESTED and os.environ.get("LAB_ALLOW_UNTESTED_SANDBOX") != "1":
        return False, ("the Linux bubblewrap wrapper in harness/platforms/linux.py is UNTESTED. Review it, then set "
                       "LAB_ALLOW_UNTESTED_SANDBOX=1 to use it. Refusing to run Hermes unsandboxed.")
    return True, ""


def prepare(mode, lab, home=None):
    return None  # nothing to generate: the policy is the argv built by wrap()


def wrap(argv, mode, lab, home=None, refresh=False):
    home = Path(home or Path.home())
    lab = Path(lab)
    xdg_cfg = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    b = ["bwrap", "--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc", "--unshare-uts",
         "--proc", "/proc", "--dev", "/dev"]
    if mode == "guard":
        b += ["--bind", "/", "/"]
        for p in (home / ".hermes", home / ".local" / "bin", xdg_cfg / "systemd" / "user", home / ".zshrc", home / ".zprofile",
                  home / ".zshenv", home / ".bashrc", home / ".bash_profile", home / ".profile"):
            if p.exists():
                b += ["--ro-bind", str(p), str(p)]
        for p in (home / ".codex", home / ".claude"):
            if p.is_dir():
                b += ["--tmpfs", str(p)]
    elif mode == "eval":
        b += ["--ro-bind", "/", "/", "--tmpfs", str(home), "--tmpfs", "/tmp", "--tmpfs", "/run/user",
              "--ro-bind", str(lab), str(lab),
              "--bind", str(lab / "hermes-home"), str(lab / "hermes-home"),
              "--bind", str(lab / "run"), str(lab / "run"),
              "--setenv", "HOME", str(lab / "run" / "sandbox-home"), "--chdir", str(lab / "run")]
        for extra in ("/mnt", "/media", "/srv"):
            if Path(extra).is_dir():
                b += ["--tmpfs", extra]
    else:
        raise ValueError(f"unknown sandbox mode '{mode}'")
    if os.environ.get("LAB_LINUX_NET") == "systemd" and mode == "eval":
        b = ["systemd-run", "--user", "--scope", "--quiet", "--collect", "-p", "IPAddressDeny=any",
             "-p", "IPAddressAllow=localhost", "--"] + b
    return b + ["--"] + list(argv)
