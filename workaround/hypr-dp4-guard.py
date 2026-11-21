#!/usr/bin/env python3
"""Guard against striped external DP output on Hyprland (amdgpu DCN 3.5).

Symptom: after the external monitor has been powered off for hours while the
GPU output sat DPMS-off, the panel comes back with fine vertical stripes.
Kernel/DRM/compositor state all look correct; framebuffer is clean. A
per-output DPMS off->on cycle (full modeset + link retrain) restores a clean
picture. This daemon watches Hyprland's event socket and performs that cycle
automatically whenever an external output (re)appears, so the first visible
frame after the blink is already correct. The internal panel is never touched.

Usage:
  hypr-dp4-guard.py           run the daemon (systemd user service)
  hypr-dp4-guard.py now [MON] cycle one output now (default: first external)
"""
import glob
import json
import os
import socket
import subprocess
import sys
import threading
import time

EXTERNAL_PREFIXES = ("DP-", "HDMI-")


def log(msg):
    print(f"hypr-dp4-guard: {msg}", flush=True)


def instance_dir():
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if sig and os.path.exists(f"{runtime}/hypr/{sig}/.socket2.sock"):
        return f"{runtime}/hypr/{sig}"
    for path in sorted(glob.glob(f"{runtime}/hypr/*/.socket2.sock")):
        return os.path.dirname(path)
    return None


def hyprctl(args, idir):
    env = dict(os.environ)
    env["HYPRLAND_INSTANCE_SIGNATURE"] = os.path.basename(idir)
    out = subprocess.run(["hyprctl", *args], capture_output=True, text=True,
                         timeout=15, env=env)
    return out.stdout.strip()


def monitors(idir):
    try:
        return json.loads(hyprctl(["monitors", "-j"], idir))
    except Exception:
        return []


def dpms_cycle(name, idir):
    # Wait until the output is fully up (present, enabled, DPMS on). In the
    # morning case the monitor appears while DPMS is still off, so allow a
    # long wait for the owner's first input to wake it.
    deadline = time.time() + 900
    while time.time() < deadline:
        m = next((m for m in monitors(idir) if m.get("name") == name), None)
        if m and m.get("dpmsStatus") and not m.get("disabled"):
            break
        time.sleep(1)
    else:
        log(f"{name} never reached DPMS-on; skipping cycle")
        return
    if not any(m.get("name") == name for m in monitors(idir)):
        log(f"{name} gone before cycle; skipping")
        return
    time.sleep(1)  # let the panel finish waking before we blink it
    log(f"cycling DPMS on {name} (stripe guard)")
    hyprctl(["dispatch", f'hl.dsp.dpms({{ action = "disable", monitor = "{name}" }})'], idir)
    time.sleep(3)
    hyprctl(["dispatch", f'hl.dsp.dpms({{ action = "enable", monitor = "{name}" }})'], idir)
    log(f"{name} DPMS cycle done")


def daemon():
    inflight = set()          # monitors currently being cycled
    last_cycle = {}           # monitor -> monotonic time of last cycle start
    lock = threading.Lock()

    def cycle_guarded(name, idir):
        try:
            dpms_cycle(name, idir)
        finally:
            with lock:
                inflight.discard(name)

    while True:
        idir = instance_dir()
        if not idir:
            time.sleep(5)
            continue
        try:
            sock = socket.socket(socket.AF_UNIX)
            sock.connect(f"{idir}/.socket2.sock")
            log(f"listening on {idir}/.socket2.sock")
            buf = sock.makefile("r", encoding="utf-8", errors="replace")
            for line in buf:
                ev, _, payload = line.strip().partition(">>")
                name = None
                # Hyprland emits both monitoradded and monitoraddedv2; take v2
                # only, and never start a second cycle for the same output
                # while one is running or just ran.
                if ev == "monitoraddedv2":
                    parts = payload.split(",")
                    name = parts[1] if len(parts) > 1 else None
                if name and name.startswith(EXTERNAL_PREFIXES):
                    with lock:
                        now = time.monotonic()
                        if name in inflight or now - last_cycle.get(name, -60) < 30:
                            name = None
                        else:
                            inflight.add(name)
                            last_cycle[name] = now
                if name:
                    log(f"external output appeared: {name}")
                    threading.Thread(target=cycle_guarded, args=(name, idir),
                                     daemon=True).start()
        except Exception as e:  # compositor restarted etc.
            log(f"socket error: {e}; retrying in 3s")
            time.sleep(3)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "now":
        idir = instance_dir()
        if not idir:
            sys.exit("no Hyprland instance found")
        target = sys.argv[2] if len(sys.argv) > 2 else next(
            (m["name"] for m in monitors(idir)
             if m["name"].startswith(EXTERNAL_PREFIXES)), None)
        if not target:
            sys.exit("no external output present")
        dpms_cycle(target, idir)
    else:
        daemon()
