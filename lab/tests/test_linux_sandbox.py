# SPDX-License-Identifier: MIT
"""Run the Linux platform module and the bubblewrap wrapper for real. No model, no Hermes.

Most classes need Linux with a bwrap that can create a sandbox; elsewhere they skip and say why.
The `linux-sandbox` CI workflow runs this file with LAB_REQUIRE_LINUX_SANDBOX=1, which turns
"the sandbox is not usable here" from a skip into a failure, and once with
LAB_EXPECT_BWRAP_BROKEN=1 while unprivileged user namespaces are restricted.

The eval-mode tests put a temporary lab copy and a marker file in the real home directory
(both removed afterwards), because hiding the real home directory is the property under test.
The guard-mode tests use a temporary directory as HOME and never touch real profile files.
"""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import _path
import platforms
from platforms import linux

ON_LINUX = sys.platform.startswith("linux")
REQUIRE = os.environ.get("LAB_REQUIRE_LINUX_SANDBOX") == "1"
EXPECT_BROKEN = os.environ.get("LAB_EXPECT_BWRAP_BROKEN") == "1"
SRC = Path(_path.HARNESS).parent
SCRIPTS = ["bin/guard", "bin/hermes", "scripts/serve_llama.sh", "scripts/serve_proxy.sh", "scripts/stop_servers.sh",
           "hermes-env.sh"]
NOTES = []


def note(text):
    """Observations worth reading in the CI log (printed once at the end of the module)."""
    if text not in NOTES:
        NOTES.append(text)


def tearDownModule():
    for n in NOTES:
        sys.stderr.write(f"NOTE: {n}\n")


def clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k not in ("LAB_LINUX_NET", "LAB_ALLOW_UNTESTED_SANDBOX")}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(extra)
    return env


def opted_in(**extra):
    return clean_env(LAB_ALLOW_UNTESTED_SANDBOX="1", **extra)


def sandbox_state():
    """(usable, reason) for the real bwrap on this machine, with the opt-in given."""
    if not ON_LINUX:
        return False, "not Linux"
    if not shutil.which("bwrap"):
        return False, "bwrap is not installed"
    with mock.patch.dict(os.environ, opted_in(), clear=True):
        return linux.available()


def require_sandbox():
    ok, why = sandbox_state()
    if ok:
        return
    if REQUIRE and not EXPECT_BROKEN:
        raise AssertionError(f"LAB_REQUIRE_LINUX_SANDBOX=1 but the sandbox is not usable: {why}")
    raise unittest.SkipTest(f"Linux sandbox not usable here: {why}")


def make_lab(parent, with_run=True):
    """A temporary copy of the lab layout. The caller removes it."""
    lab = Path(tempfile.mkdtemp(prefix="las-lab-test-", dir=str(parent))).resolve()
    for d in ("harness", "fixtures", "fixtures_heldout", "bin", "scripts"):
        shutil.copytree(SRC / d, lab / d, ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy2(SRC / "hermes-env.sh", lab / "hermes-env.sh")
    (lab / "hermes-home").mkdir()
    if with_run:
        (lab / "run").mkdir()
    return lab


def sx(lab, mode, *cmd, env=None, **kw):
    """Run `cmd` through the lab copy's sandbox_exec.py."""
    kw.setdefault("timeout", 120)
    return subprocess.run([sys.executable, str(lab / "harness" / "sandbox_exec.py"), "--mode", mode, "--", *cmd],
                          env=env or opted_in(), stdin=subprocess.DEVNULL, capture_output=True, text=True, **kw)


def sh(lab, mode, script, **kw):
    return sx(lab, mode, "sh", "-c", script, **kw)


def inside_python():
    """The interpreter to use inside eval mode, where the home directory is hidden."""
    home = str(Path.home().resolve()) + os.sep
    for p in (sys.executable, os.path.realpath(sys.executable)):
        if (p + os.sep).startswith(home):
            raise unittest.SkipTest("this Python interpreter lives in the home directory, which eval mode hides")
    return sys.executable


def primary_ip():
    """This host's main non-loopback IPv4 address, or None. Sends nothing."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return None if ip.startswith("127.") else ip


class _Hello(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"lab-ok"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class http_server:
    def __init__(self, host):
        self.srv = ThreadingHTTPServer((host, 0), _Hello)
        self.url = f"http://{host}:{self.srv.server_address[1]}/"

    def __enter__(self):
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self.url

    def __exit__(self, *exc):
        self.srv.shutdown()
        self.srv.server_close()


FETCH = ("import sys,urllib.request\n"
         "o=urllib.request.build_opener(urllib.request.ProxyHandler({}))\n"
         "print(o.open(sys.argv[1],timeout=5).read().decode())\n")


# --------------------------------------------------------------------------- any POSIX system
class FakeBwrap(unittest.TestCase):
    """available() against stand-in bwrap executables: runs on macOS too."""

    def setUp(self):
        if os.name != "posix":
            self.skipTest("needs a POSIX shell")
        self.dir = Path(tempfile.mkdtemp(prefix="las-fake-bwrap-"))
        self.addCleanup(shutil.rmtree, self.dir, ignore_errors=True)

    def fake(self, body):
        p = self.dir / "bwrap"
        p.write_text("#!/bin/sh\n" + body + "\n")
        p.chmod(0o755)
        return {"PATH": str(self.dir) + os.pathsep + os.defpath}

    def test_bwrap_that_cannot_create_a_sandbox_is_reported_and_refused(self):
        env = self.fake('echo "bwrap: setting up uid map: Permission denied" >&2; exit 1')
        with mock.patch.dict(os.environ, opted_in(**env), clear=True):
            ok, why = linux.available()
        self.assertFalse(ok)
        self.assertIn("setting up uid map: Permission denied", why)
        self.assertIn("user namespaces", why)
        self.assertIn("kernel.apparmor_restrict_unprivileged_userns", why)
        self.assertIn("Refusing", why)

    def test_working_bwrap_still_needs_the_opt_in(self):
        env = self.fake("exit 0")
        with mock.patch.dict(os.environ, clean_env(**env), clear=True):
            ok, why = linux.available()
            self.assertFalse(ok)
            self.assertIn("LAB_ALLOW_UNTESTED_SANDBOX=1", why)
        with mock.patch.dict(os.environ, opted_in(**env), clear=True):
            self.assertEqual(linux.available(), (True, ""))

    def test_unknown_network_setting_is_refused(self):
        env = self.fake("exit 0")
        with mock.patch.dict(os.environ, opted_in(LAB_LINUX_NET="Systemd", **env), clear=True):
            ok, why = linux.available()
        self.assertFalse(ok)
        self.assertIn("LAB_LINUX_NET", why)

    def test_network_filter_that_is_not_enforced_is_refused(self):
        env = self.fake("exit 0")
        for rc, expect in ((2, "NOT enforced"), (3, "could not tell"), (1, "could not be started")):
            (self.dir / "systemd-run").write_text(f"#!/bin/sh\necho 'Failed to connect to bus' >&2\nexit {rc}\n")
            (self.dir / "systemd-run").chmod(0o755)
            with mock.patch.dict(os.environ, opted_in(LAB_LINUX_NET="systemd", **env), clear=True):
                ok, why = linux.available()
            self.assertFalse(ok, rc)
            self.assertIn(expect, why)
        (self.dir / "systemd-run").write_text("#!/bin/sh\nexit 0\n")
        with mock.patch.dict(os.environ, opted_in(LAB_LINUX_NET="systemd", **env), clear=True):
            self.assertEqual(linux.available(), (True, ""))

    def test_eval_argv_order(self):
        with mock.patch.dict(os.environ, clean_env(), clear=True):
            argv = linux.wrap(["x"], "eval", "/srv/lab", home="/data/homes/example")
        lab_bind = argv.index("/srv/lab") - 1
        self.assertEqual(argv[lab_bind], "--ro-bind")
        root_bind = argv.index("--ro-bind")
        self.assertEqual(argv[root_bind + 1:root_bind + 3], ["/", "/"])
        for flag in ("--proc", "--dev"):                 # after the bind of /, or that bind would cover them
            self.assertGreater(argv.index(flag), root_bind)
        for i, a in enumerate(argv):                     # every tmpfs before the lab binds
            if a == "--tmpfs":
                self.assertLess(i, lab_bind, argv[i + 1])
        i = argv.index("--dir")
        self.assertEqual(argv[i + 1], "/srv/lab/run/sandbox-home")
        self.assertGreater(i, argv.index("/srv/lab/run"))
        self.assertEqual(argv[argv.index("HOME") + 1], "/srv/lab/run/sandbox-home")
        self.assertNotIn("systemd-run", argv)
        with mock.patch.dict(os.environ, clean_env(LAB_LINUX_NET="systemd"), clear=True):
            self.assertEqual(linux.wrap(["x"], "eval", "/srv/lab", home="/data/homes/example")[0], "systemd-run")
            self.assertEqual(linux.wrap(["x"], "guard", "/srv/lab", home="/data/homes/example")[0], "bwrap")


class ShellSyntax(unittest.TestCase):
    def test_bash_syntax(self):
        if not shutil.which("bash"):
            self.skipTest("bash not found")
        for s in SCRIPTS:
            r = subprocess.run(["bash", "-n", str(SRC / s)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f"{s}: {r.stderr}")

    def test_shellcheck(self):
        if not shutil.which("shellcheck"):
            self.skipTest("shellcheck not found")
        r = subprocess.run(["shellcheck", "-s", "bash", "-S", "warning"] + [str(SRC / s) for s in SCRIPTS],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


# --------------------------------------------------------------------------- Linux, no bwrap needed
@unittest.skipUnless(ON_LINUX, "not Linux")
class LinuxPlatformInterface(unittest.TestCase):
    def test_system(self):
        self.assertEqual(platforms.system(), "linux")

    def test_directories_with_xdg_variables(self):
        env = {"HOME": "/h/u", "XDG_STATE_HOME": "/x/state", "XDG_CONFIG_HOME": "/x/cfg", "XDG_DATA_HOME": "/x/data"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(platforms.state_dir("app"), Path("/x/state/app"))
            self.assertEqual(platforms.config_dir("app"), Path("/x/cfg/app"))
            self.assertEqual(platforms.data_dir("app"), Path("/x/data/app"))

    def test_directories_without_xdg_variables(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("XDG_")}
        with mock.patch.dict(os.environ, env, clear=True):
            home = Path(os.environ.get("HOME") or Path.home())
            self.assertEqual(platforms.state_dir("app"), home / ".local" / "state" / "app")
            self.assertEqual(platforms.config_dir("app"), home / ".config" / "app")
            self.assertEqual(platforms.data_dir("app"), home / ".local" / "share" / "app")
        env.pop("HOME", None)
        with mock.patch.dict(os.environ, env, clear=True):          # no HOME either: the password database
            self.assertEqual(platforms.config_dir("app"), Path.home() / ".config" / "app")

    def test_service_notes_and_notify(self):
        self.assertIn("systemd user unit", platforms.service_notes())
        self.assertIs(platforms.notify("t", "b"), False)


@unittest.skipUnless(ON_LINUX, "not Linux")
class RestrictedUserns(unittest.TestCase):
    """bwrap is installed but may not create user namespaces (Ubuntu 24.04 default). CI produces this state."""

    def test_fail_closed_with_a_reason(self):
        if not shutil.which("bwrap"):
            self.skipTest("bwrap is not installed")
        ok, why = sandbox_state()
        if ok:
            if EXPECT_BROKEN:
                self.fail("LAB_EXPECT_BWRAP_BROKEN=1 but bwrap can create a sandbox")
            self.skipTest("bwrap can create a sandbox here, so the restricted state cannot be observed")
        note(f"restricted state: available() said: {why}")
        self.assertIn("cannot create a sandbox", why)
        self.assertIn("user namespaces", why)
        with mock.patch.dict(os.environ, opted_in(), clear=True):
            with self.assertRaises(platforms.SandboxUnavailable):
                platforms.get_sandbox()
        tmp = Path(tempfile.mkdtemp(prefix="las-restricted-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        r = subprocess.run([sys.executable, str(SRC / "harness" / "sandbox_exec.py"), "--mode", "guard", "--",
                            "sh", "-c", f"echo ran > '{tmp}/ran'"], env=opted_in(), capture_output=True, text=True)
        self.assertEqual(r.returncode, 78, r.stderr)
        self.assertIn("refusing to run", r.stderr)
        self.assertFalse((tmp / "ran").exists())


# --------------------------------------------------------------------------- Linux with a working bwrap
@unittest.skipUnless(ON_LINUX, "not Linux")
class Availability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_sandbox()
        cls.tmp = Path(tempfile.mkdtemp(prefix="las-avail-"))
        cls.addClassCleanup(shutil.rmtree, cls.tmp, ignore_errors=True)
        cls.lab = make_lab(cls.tmp)
        cls.empty = cls.tmp / "empty-path"
        cls.empty.mkdir()

    def refused(self, env, expect):
        ran = self.lab / "run" / f"ran-{uuid.uuid4().hex}"
        for mode in ("guard", "eval"):
            r = sx(self.lab, mode, "/bin/sh", "-c", f"echo ran > '{ran}'", env=env)
            self.assertEqual(r.returncode, 78, r.stderr)
            self.assertIn("sandbox unavailable, refusing to run", r.stderr)
            self.assertIn(expect, r.stderr)
            self.assertEqual(r.stdout, "")
            self.assertFalse(ran.exists(), "the command ran although no sandbox was available")

    def test_without_bwrap_on_path(self):
        env = opted_in(PATH=str(self.empty))
        with mock.patch.dict(os.environ, env, clear=True):
            ok, why = linux.available()
            self.assertFalse(ok)
            self.assertIn("not found", why)
            with self.assertRaises(platforms.SandboxUnavailable):
                platforms.get_sandbox()
        self.refused(env, "not found")

    def test_without_the_opt_in(self):
        with mock.patch.dict(os.environ, clean_env(), clear=True):
            ok, why = linux.available()
            self.assertFalse(ok)
            self.assertIn("LAB_ALLOW_UNTESTED_SANDBOX=1", why)
            with self.assertRaises(platforms.SandboxUnavailable):
                platforms.get_sandbox()
        self.refused(clean_env(), "LAB_ALLOW_UNTESTED_SANDBOX=1")
        self.refused(clean_env(LAB_ALLOW_UNTESTED_SANDBOX="yes"), "LAB_ALLOW_UNTESTED_SANDBOX=1")

    def test_with_the_opt_in(self):
        with mock.patch.dict(os.environ, opted_in(), clear=True):
            self.assertEqual(linux.available(), (True, ""))
            self.assertIs(platforms.get_sandbox(), linux)

    def test_unknown_network_setting(self):
        self.refused(opted_in(LAB_LINUX_NET="none"), "LAB_LINUX_NET")


@unittest.skipUnless(ON_LINUX, "not Linux")
class EvalMode(unittest.TestCase):
    """Eval mode with the lab inside the real home directory (the usual layout)."""

    @classmethod
    def setUpClass(cls):
        require_sandbox()
        cls.home = Path.home().resolve()
        if len(cls.home.parts) < 2 or not os.access(cls.home, os.W_OK):
            raise unittest.SkipTest("no writable home directory")
        cls.lab = make_lab(cls.home)
        cls.addClassCleanup(shutil.rmtree, cls.lab, ignore_errors=True)
        cls.marker = cls.home / f".las-sandbox-test-marker-{uuid.uuid4().hex}"
        cls.marker.write_text("outside\n")
        cls.addClassCleanup(lambda: cls.marker.unlink(missing_ok=True))

    def test_exit_codes_propagate(self):
        self.assertEqual(sx(self.lab, "eval", "true").returncode, 0)
        self.assertEqual(sx(self.lab, "eval", "false").returncode, 1)
        self.assertEqual(sh(self.lab, "eval", "exit 7").returncode, 7)
        r = sh(self.lab, "eval", "echo out; echo err >&2")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "out\n", "err\n"))
        self.assertNotEqual(sx(self.lab, "eval", "las-no-such-command").returncode, 0)

    def test_real_home_is_hidden(self):
        self.assertTrue(self.marker.exists())
        r = sh(self.lab, "eval", f"test -e '{self.marker}'")
        self.assertEqual(r.returncode, 1, r.stderr)
        r = sx(self.lab, "eval", "ls", "-A", str(self.home))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.split(), [self.lab.relative_to(self.home).parts[0]])

    def test_lab_is_read_only(self):
        r = sh(self.lab, "eval", f"echo x > '{self.lab}/harness/x'")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Read-only file system", r.stderr)
        self.assertFalse((self.lab / "harness" / "x").exists())
        self.assertNotEqual(sh(self.lab, "eval", f"rm '{self.lab}/hermes-env.sh'").returncode, 0)
        self.assertNotEqual(sh(self.lab, "eval", f"mkdir '{self.lab}/newdir'").returncode, 0)
        r = sx(self.lab, "eval", "cat", str(self.lab / "hermes-env.sh"))
        self.assertEqual(r.stdout, (self.lab / "hermes-env.sh").read_text())

    def test_run_and_hermes_home_are_writable(self):
        for d in ("run", "hermes-home"):
            r = sh(self.lab, "eval", f"echo inside > '{self.lab}/{d}/w.txt'")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((self.lab / d / "w.txt").read_text(), "inside\n")

    def test_tmp_is_private(self):
        fd, outside = tempfile.mkstemp(prefix="las-outside-", dir="/tmp")
        os.close(fd)
        self.addCleanup(os.unlink, outside)
        name = f"/tmp/las-inside-{uuid.uuid4().hex}"
        r = sh(self.lab, "eval", f"test -e '{outside}' && exit 9; ls -A /tmp; echo x > '{name}' && test -s '{name}'")
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
        self.assertFalse(os.path.exists(name))

    def test_home_is_the_sandbox_home_and_it_exists(self):
        fresh = make_lab(self.home)                      # nothing has created run/sandbox-home in this one
        self.addCleanup(shutil.rmtree, fresh, ignore_errors=True)
        r = sh(fresh, "eval", 'echo "$HOME"; pwd; test -d "$HOME" && echo x > "$HOME/w" && cd && pwd')
        self.assertEqual(r.returncode, 0, r.stderr)
        sandbox_home = fresh / "run" / "sandbox-home"
        self.assertEqual(r.stdout.split(), [str(sandbox_home), str(fresh / "run"), str(sandbox_home)])
        self.assertEqual((sandbox_home / "w").read_text(), "x\n")

    def test_pid_namespace_is_new(self):
        r = sh(self.lab, "eval", "echo $$; ls /proc | grep -c '^[0-9]'")
        self.assertEqual(r.returncode, 0, r.stderr)
        pid, count = (int(x) for x in r.stdout.split())
        host = sum(1 for p in os.listdir("/proc") if p.isdigit())
        note(f"eval mode: shell pid inside {pid}, {count} processes visible inside, {host} outside")
        self.assertLessEqual(pid, 3)
        self.assertLessEqual(count, 5)
        self.assertGreater(host, count)

    def test_run_is_hidden(self):
        uid_dir = Path("/run/user") / str(os.getuid())
        present = [p for p in (uid_dir / "bus", uid_dir, Path("/run/user"), Path("/run/dbus/system_bus_socket"),
                               Path("/run/docker.sock")) if p.exists()]
        note("on the host, before sandboxing: " + (", ".join(
            str(p).replace(str(os.getuid()), "<uid>") for p in present) or "none of the checked /run paths") + " present")
        r = sx(self.lab, "eval", "ls", "-A", "/run")
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
        r = sh(self.lab, "eval", "test -e /run/user || test -e /var/run/dbus/system_bus_socket || test -e /run/docker.sock")
        self.assertEqual(r.returncode, 1)

    def test_rest_of_the_filesystem_is_read_only(self):
        for d in ("/etc", "/usr", "/var/tmp", "/"):
            r = sh(self.lab, "eval", f"echo x > '{d}/las-sandbox-test'")
            self.assertNotEqual(r.returncode, 0, d)
            self.assertFalse(os.path.exists(f"{d}/las-sandbox-test"))

    def test_mount_directories_are_empty(self):
        for d in ("/mnt", "/media", "/srv"):
            if os.path.isdir(d):
                r = sx(self.lab, "eval", "ls", "-A", d)
                self.assertEqual((r.returncode, r.stdout), (0, ""), d)

    def test_missing_run_directory_fails_closed(self):
        bare = make_lab(self.home, with_run=False)
        self.addCleanup(shutil.rmtree, bare, ignore_errors=True)
        r = sh(bare, "eval", f"echo ran > '{bare}/hermes-home/ran'")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((bare / "hermes-home" / "ran").exists())

    def test_dies_with_its_parent(self):
        beat = self.lab / "run" / "beat"
        loop = f"while :; do date +%s%N > '{beat}'; sleep 0.2; done"
        cmd = [sys.executable, str(self.lab / "harness" / "sandbox_exec.py"), "--mode", "eval", "--", "sh", "-c", loop]
        parent = subprocess.Popen([sys.executable, "-c", "import subprocess,sys,time\nsubprocess.Popen(sys.argv[1:])\ntime.sleep(600)"] + cmd,
                                  env=opted_in(), stdin=subprocess.DEVNULL, start_new_session=True)

        def cleanup():
            try:
                os.killpg(parent.pid, signal.SIGKILL)
            except OSError:
                pass
            parent.wait()
        self.addCleanup(cleanup)
        deadline = time.time() + 30
        while not beat.exists() and time.time() < deadline:
            time.sleep(0.1)
        self.assertTrue(beat.exists(), "the sandboxed loop never started")
        a = beat.read_text()
        time.sleep(1)
        self.assertNotEqual(a, beat.read_text(), "the sandboxed loop is not running")
        os.kill(parent.pid, signal.SIGKILL)              # only the parent: bwrap and the loop are separate processes
        parent.wait()
        time.sleep(1.5)
        a = beat.read_text()
        time.sleep(1.5)
        self.assertEqual(a, beat.read_text(), "the sandboxed process survived its parent")


@unittest.skipUnless(ON_LINUX, "not Linux")
class EvalModeLabUnderTmp(unittest.TestCase):
    """The lab under /tmp, which eval mode replaces: the lab binds must come after that."""

    @classmethod
    def setUpClass(cls):
        require_sandbox()
        cls.lab = make_lab("/tmp")
        cls.addClassCleanup(shutil.rmtree, cls.lab, ignore_errors=True)

    def test_lab_is_visible_read_only_and_run_is_writable(self):
        r = sh(self.lab, "eval", f"ls /tmp; echo inside > '{self.lab}/run/w.txt'; echo x > '{self.lab}/harness/x'")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout.split(), [self.lab.name])
        self.assertEqual((self.lab / "run" / "w.txt").read_text(), "inside\n")
        self.assertFalse((self.lab / "harness" / "x").exists())
        r = sx(self.lab, "eval", "ls", "-A", str(Path.home().resolve()))
        self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)


@unittest.skipUnless(ON_LINUX, "not Linux")
class EvalNetwork(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        require_sandbox()
        cls.py = inside_python()
        cls.lab = make_lab(Path.home().resolve())
        cls.addClassCleanup(shutil.rmtree, cls.lab, ignore_errors=True)

    def fetch(self, url, **env):
        return sx(self.lab, "eval", self.py, "-c", FETCH, url, env=opted_in(**env))

    def test_loopback_server_outside_is_reachable(self):
        with http_server("127.0.0.1") as url:
            r = self.fetch(url)
        self.assertEqual((r.returncode, r.stdout), (0, "lab-ok\n"), r.stderr)

    def test_outbound_network_is_not_filtered_by_default(self):
        """Not a property anyone wants: this pins the documented gap. If it starts failing, update the docs."""
        ip = primary_ip()
        if not ip:
            self.skipTest("this host has no non-loopback IPv4 address to connect to")
        with http_server(ip) as url:
            r = self.fetch(url)
        self.assertEqual((r.returncode, r.stdout), (0, "lab-ok\n"), r.stderr)
        note("eval mode without LAB_LINUX_NET: a TCP connection to this host's non-loopback address succeeded (egress is NOT filtered)")

    def test_systemd_address_filter(self):
        if not shutil.which("systemd-run"):
            self.skipTest("systemd-run not found")
        with mock.patch.dict(os.environ, opted_in(LAB_LINUX_NET="systemd"), clear=True):
            ok, why = linux.available()
        if not ok:
            ran = self.lab / "run" / "ran-net"
            r = sh(self.lab, "eval", f"echo ran > '{ran}'", env=opted_in(LAB_LINUX_NET="systemd"))
            self.assertEqual(r.returncode, 78, r.stderr)
            self.assertFalse(ran.exists())
            note(f"LAB_LINUX_NET=systemd refused (exit 78, command not run): {why}")
            self.skipTest(f"LAB_LINUX_NET=systemd is not usable here, and the wrapper refused to run: {why}")
        with http_server("127.0.0.1") as url:
            r = self.fetch(url, LAB_LINUX_NET="systemd")
        self.assertEqual((r.returncode, r.stdout), (0, "lab-ok\n"), r.stderr)
        ip = primary_ip()
        if not ip:
            self.skipTest("loopback works under the filter; no non-loopback IPv4 address to test the deny rule against")
        with http_server(ip) as url:
            r = self.fetch(url, LAB_LINUX_NET="systemd")
        self.assertNotEqual(r.returncode, 0, "a non-loopback connection succeeded under IPAddressDeny=any")
        note("LAB_LINUX_NET=systemd: loopback reachable, non-loopback connection blocked")


@unittest.skipUnless(ON_LINUX, "not Linux")
class EvalMcpServer(unittest.TestCase):
    """The lab's MCP tool server, started the way Hermes would start it, inside eval mode."""

    @classmethod
    def setUpClass(cls):
        require_sandbox()
        cls.py = inside_python()

    def session(self, lab, requests):
        text = "".join(json.dumps(r) + "\n" for r in requests)
        r = subprocess.run([sys.executable, str(lab / "harness" / "sandbox_exec.py"), "--mode", "eval", "--",
                            self.py, str(lab / "harness" / "mcp_server.py")],
                           env=opted_in(), input=text, capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        return {m["id"]: m for m in (json.loads(line) for line in r.stdout.splitlines())}

    def lab_copy(self):
        lab = make_lab(Path.home().resolve())
        self.addCleanup(shutil.rmtree, lab, ignore_errors=True)
        return lab

    def test_initialize_list_and_call(self):
        lab = self.lab_copy()
        out = self.session(lab, [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "reminder_list", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "no/such"}])
        self.assertEqual(sorted(out), [1, 2, 3, 4])
        self.assertEqual(out[1]["result"]["serverInfo"]["name"], "lab")
        names = [t["name"] for t in out[2]["result"]["tools"]]
        self.assertIn("reminder_list", names)
        self.assertIn("send_message", names)
        result = json.loads(out[3]["result"]["content"][0]["text"])
        self.assertNotIn("error", result)
        self.assertEqual(out[4]["error"]["code"], -32601)
        calls = [json.loads(line) for line in (lab / "run" / "mcp_calls.jsonl").read_text().splitlines()]
        self.assertEqual([c["name"] for c in calls], ["reminder_list"])
        self.assertEqual(calls[0]["result"], result)
        self.assertIn("reminders", json.loads((lab / "run" / "mcp_world.json").read_text()))

    def test_gated_call_writes_the_event_log_under_run(self):
        lab = self.lab_copy()
        (lab / "run" / "mcp_task.json").write_text(json.dumps({"gate": True, "nonce": "t1"}))
        out = self.session(lab, [{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": "send_message", "arguments": {"to": "Mom", "body": "On my way"}}}])
        result = json.loads(out[1]["result"]["content"][0]["text"])
        self.assertIn("confirmation_id", result)
        events = [json.loads(line) for line in (lab / "run" / "gate_events.jsonl").read_text().splitlines()]
        self.assertEqual([(e["type"], e["confirmation_id"]) for e in events], [("pending", result["confirmation_id"])])
        self.assertEqual(json.loads((lab / "run" / "mcp_world.json").read_text())["sent"], [])


@unittest.skipUnless(ON_LINUX, "not Linux")
class GuardMode(unittest.TestCase):
    """Guard mode with a temporary directory as HOME: no real profile file is touched."""

    @classmethod
    def setUpClass(cls):
        require_sandbox()
        cls.home = Path(tempfile.mkdtemp(prefix="las-guard-home-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.home, ignore_errors=True)
        cls.lab = make_lab(cls.home)
        cls.files = [".hermes/config.yaml", ".local/bin/tool", ".config/systemd/user/unit.service", ".bashrc", ".profile",
                     ".zshrc", ".claude/credentials.json", ".codex/auth.json", ".claude.json", "notes.txt"]
        for f in cls.files:
            (cls.home / f).parent.mkdir(parents=True, exist_ok=True)
            (cls.home / f).write_text(f"original {f}\n")
        cls.env = {k: v for k, v in opted_in(HOME=str(cls.home)).items() if k != "XDG_CONFIG_HOME"}

    def g(self, script):
        return sh(self.lab, "guard", script, env=self.env)

    def test_exit_codes_and_environment(self):
        self.assertEqual(self.g("exit 0").returncode, 0)
        self.assertEqual(self.g("exit 7").returncode, 7)
        r = self.g('echo "$HOME"')
        self.assertEqual(r.stdout.strip(), str(self.home))

    def test_protected_paths_are_read_only_and_readable(self):
        for f in self.files[:6]:
            p = self.home / f
            r = self.g(f"cat '{p}'")
            self.assertEqual(r.stdout, f"original {f}\n", f)
            for script in (f"echo changed >> '{p}'", f"rm -f '{p}'", f"mv '{p}' '{p}.moved'"):
                self.assertNotEqual(self.g(script).returncode, 0, script.replace(str(self.home), "~"))
            self.assertEqual(p.read_text(), f"original {f}\n", f)
            self.assertFalse(Path(str(p) + ".moved").exists())
        for d in (".hermes", ".local/bin", ".config/systemd/user"):
            self.assertNotEqual(self.g(f"echo new > '{self.home}/{d}/new'").returncode, 0, d)
            self.assertFalse((self.home / d / "new").exists())

    def test_other_agents_login_stores_appear_empty(self):
        r = self.g(f"ls -A '{self.home}/.claude' '{self.home}/.codex' | grep -v ':$' | grep -c .; cat '{self.home}/.claude.json'")
        self.assertEqual(r.stdout, "0\n", r.stderr)
        self.g(f"echo x > '{self.home}/.claude/planted'; echo x > '{self.home}/.claude.json'")
        self.assertFalse((self.home / ".claude" / "planted").exists())
        for f in self.files[6:9]:
            self.assertEqual((self.home / f).read_text(), f"original {f}\n", f)

    def test_everything_else_stays_writable(self):
        r = self.g(f"echo inside >> '{self.home}/notes.txt' && echo new > '{self.home}/new.txt' && echo l > '{self.lab}/harness/guard-wrote'")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.home / "notes.txt").read_text(), "original notes.txt\ninside\n")
        self.assertTrue((self.home / "new.txt").exists())
        self.assertTrue((self.lab / "harness" / "guard-wrote").exists())

    def test_pid_namespace_is_new(self):
        r = self.g("echo $$; ls /proc | grep -c '^[0-9]'")
        pid, count = (int(x) for x in r.stdout.split())
        self.assertLessEqual(pid, 3)
        self.assertLessEqual(count, 5)

    def test_profile_file_missing_at_start_is_not_protected(self):
        """Pins a documented difference from macOS: only files that exist can be bound read-only."""
        target = self.home / ".zprofile"
        self.assertFalse(target.exists())
        self.addCleanup(lambda: target.unlink(missing_ok=True))
        self.assertEqual(self.g(f"echo planted > '{target}'").returncode, 0)
        self.assertTrue(target.exists())
        note("guard mode: a shell profile file that did not exist when the sandbox started could be created (not protected)")


@unittest.skipUnless(ON_LINUX, "not Linux")
class ShellHelpers(unittest.TestCase):
    """The bash helpers, as far as they go without a model server or Hermes."""

    @classmethod
    def setUpClass(cls):
        if not shutil.which("bash"):
            raise unittest.SkipTest("bash not found")
        cls.home = Path(tempfile.mkdtemp(prefix="las-helpers-home-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.home, ignore_errors=True)
        cls.lab = make_lab(cls.home)
        (cls.lab / "logs").mkdir()
        subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(cls.lab / ".venv")], check=True,
                       capture_output=True, timeout=300)
        cls.env = opted_in(HOME=str(cls.home))
        cls.env.pop("LAB", None)

    def script(self, name, *args, env=None):
        return subprocess.run([str(self.lab / name), *args], env=env or self.env, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, timeout=120)

    def test_stop_servers_with_nothing_running(self):
        r = self.script("scripts/stop_servers.sh")
        self.assertEqual((r.returncode, r.stderr), (0, ""), r.stdout)
        self.assertIn("no lab server processes running", r.stdout)

    def test_stop_servers_stops_a_process_named_in_a_pid_file(self):
        p = subprocess.Popen(["sleep", "300"])
        self.addCleanup(p.kill)
        pid_file = self.lab / "run" / "sleeper.pid"
        pid_file.write_text(f"{p.pid}\n")
        (self.lab / "run" / "stale.pid").write_text("999999999\n")
        r = self.script("scripts/stop_servers.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(p.wait(timeout=10), -signal.SIGTERM)
        self.assertEqual(list((self.lab / "run").glob("*.pid")), [])

    def test_serve_proxy_then_stop_servers(self):
        if not shutil.which("lsof"):
            self.skipTest("lsof not found (the serve scripts use it to check the port)")
        probe = socket.socket()
        try:
            probe.bind(("127.0.0.1", 18432))
        except OSError:
            self.skipTest("port 18432 is in use on this machine")
        finally:
            probe.close()
        self.addCleanup(self.script, "scripts/stop_servers.sh")
        r = self.script("scripts/serve_proxy.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("proxy ready", r.stdout)
        socket.create_connection(("127.0.0.1", 18432), timeout=5).close()
        busy = self.script("scripts/serve_proxy.sh")                 # second start: the lsof port check
        self.assertEqual(busy.returncode, 1)
        self.assertIn("port 18432 busy", busy.stderr)
        r = self.script("scripts/stop_servers.sh")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((self.lab / "run" / "proxy.pid").exists())
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", 18432), timeout=2).close()

    def test_bin_guard(self):
        require_sandbox()
        self.assertEqual(self.script("bin/guard", "true").returncode, 0)
        self.assertEqual(self.script("bin/guard", "sh", "-c", "exit 5").returncode, 5)
        r = self.script("bin/guard", "sh", "-c", 'echo "$HERMES_HOME"; echo "$LAB"')
        self.assertEqual(r.stdout.split(), [str(self.lab / "hermes-home"), str(self.lab)], r.stderr)
        env = {k: v for k, v in self.env.items() if k != "LAB_ALLOW_UNTESTED_SANDBOX"}
        ran = self.lab / "run" / "guard-ran"
        r = self.script("bin/guard", "sh", "-c", f"echo ran > '{ran}'", env=env)
        self.assertEqual(r.returncode, 78, r.stderr)
        self.assertFalse(ran.exists())


if __name__ == "__main__":
    unittest.main()
