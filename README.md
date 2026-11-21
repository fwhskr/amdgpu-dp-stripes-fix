# amdgpu-dp-stripes-fix

External DisplayPort monitor shows **fine grey vertical stripes (unreadable)** after being
powered off overnight, on an AMD Strix Halo (DCN 3.5.1) system that stays awake.
This repo tracks the root-cause hunt, the eventual kernel patch, and a re-apply kit so the
fix survives an OS reinstall until it lands upstream.

**Status: root cause under investigation. Interim workaround available (below).**

## Symptom and evidence (2026-11-21)

Hardware: openSUSE Tumbleweed, kernel 7.3.4, AMD Radeon 8060S (Strix Halo, DCN 3.5.1),
Hyprland 0.57.2 / Aquamarine 0.16. External LG Ultrawide 5120x2160@72 Hz, 8 bpc RGB,
no DSC, DisplayPort HBR3 x4 through a Thunderbolt (USB4/DPIA) dock. Internal eDP panel
2560x1600@165 always fine.

Nightly sequence: monitor powered off with its own button (~8 h) = full DRM hotplug
removal. System stays **awake** (workloads running); hypridle puts outputs in DPMS-off
after 10 min, so the display hardware idles for hours. In the morning, switching the
monitor on gives a panel full of fine vertical stripes.

Established facts:

- Kernel/DRM/compositor state while striped looks **completely normal**
  (5120x2160@72, CRTC active). Framebuffer screenshots are **clean** — the corruption
  happens between GPU scanout and the panel.
- DPCD readback while striped: link HBR3 x4, all lanes locked, DSC off.
- Stripes **survive** cable replug, dock power-cycle, monitor power-cycle — i.e. multiple
  full hotplug remove/re-add cycles with fresh compositor modesets.
- Stripes are **cured** by a software DPMS off->on cycle of all outputs (no reboot).
  Whether a per-output cycle of the external output alone also cures it is the key open
  discriminator (it distinguishes per-stream state from global DC/IPS state).
- Short monitor power cycles (30 s, 5 min) do **not** reproduce it — the trigger needs
  the long idle / DPMS-off residency.
- Known related fixes are already present in 7.3.4 (DCN35 periodic-detection restore,
  DPMS partially-updated-pipe-context fix), and no exact upstream duplicate was found in
  gitlab.freedesktop.org/drm/amd (closest: drm/amd#5318, different symptom).

Leading hypotheses (to be discriminated): DC idle-power-state (IPS/DMUB) exit restoring
5120-wide ODM-combine pipe state incorrectly; stuck long-term link/stream state that only
a full stream disable resets.

## If you hit it right now (no reboot needed)

```bash
# Hyprland:
hyprctl dispatch 'hl.dsp.dpms({ action = "disable" })'; sleep 4
hyprctl dispatch 'hl.dsp.dpms({ action = "enable" })'
```

## Interim workaround (automatic)

`workaround/hypr-dp4-guard.py` — a systemd user service that watches Hyprland's event
socket and DPMS-cycles an external output once when it (re)appears and wakes, so the
first settled frame is already clean (~3 s blink on that output only).

```bash
cp workaround/hypr-dp4-guard.py ~/.local/bin/
cp workaround/hypr-dp4-guard.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now hypr-dp4-guard.service
```

Manual one-shot: `python3 ~/.local/bin/hypr-dp4-guard.py now`

## Evidence capture (for the upstream report)

Run **while striped, before** any DPMS cycle or replug:

```bash
tools/stripes-capture.sh striped-1
# then cure, and capture the known-good state for diffing:
tools/stripes-capture.sh clean-1
```

## Proper fix (planned)

1. Capture striped-vs-clean evidence (DRM state, DPCD, DTN log where lockdown permits)
   plus the per-output-vs-global DPMS discriminator.
2. A/B probes: `amdgpu.dcdebugmask=0x800` (DC_DISABLE_IPS), `=0x200000`
   (DC_SKIP_DETECTION_LT) to localize IPS vs link-training.
3. Write the minimal kernel patch, keep it in `patches/<kernel-version>/`, build and
   sign only the `amdgpu` module, prove it over multiple overnight cycles.
4. `reapply.sh` will apply, build, sign and install the patched module for the
   currently installed kernel (Secure Boot: one-time MOK enrollment of your own key).
5. File the bug at gitlab.freedesktop.org/drm/amd and submit the patch to the
   amd-gfx mailing list (kernel patches do not go in as GitLab/GitHub PRs).

## License

GPL-2.0-only (same as the kernel code any patch here touches).
