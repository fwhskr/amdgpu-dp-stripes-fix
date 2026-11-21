# Upstream issue draft (gitlab.freedesktop.org/drm/amd)

Title: [DCN 3.5.1 / Strix Halo] External DP 5120x2160 shows vertical stripes after
monitor power-off + long DPMS-off; survives hotplug, cured by DPMS cycle

## Brief summary of the problem

After the external monitor has been powered off for hours while the system stayed
awake with outputs in DPMS-off, powering the monitor back on produces fine vertical
stripes over the whole panel (unreadable). DRM/compositor state and framebuffer
captures are clean; the corruption is between scanout and panel. The stripes survive
cable replug and dock/monitor power-cycles (full hotplug remove/re-add + fresh
modesets). A software DPMS off->on of all outputs cures them instantly. A reboot also
cures them. The internal eDP panel is never affected.

## Hardware description

- CPU/GPU: AMD Strix Halo, Radeon 8060S Graphics (amdgpu, DCN 3.5.1)
  (attach `lspci -k` output)
- System RAM: (fill in)
- Displays:
  - eDP-1: BOE NE140QDM-NX8 2560x1600@165 (internal, always correct)
  - DP-4: LG ULTRAWIDE 5120x2160@72, 8 bpc RGB, no DSC, HBR3 x4, via UGREEN TBT5
    Thunderbolt dock (USB4 DP tunnelling / DPIA)

## System information

- Distro / kernel: openSUSE Tumbleweed, kernel 7.3.4-1-default
- Compositor: Hyprland 0.57.2 (Aquamarine 0.16), Wayland/DRM-KMS
- (attach `dmesg | grep -i 'display core'`, `amdgpu_firmware_info`)

## How to reproduce

1. External 5120x2160 DP monitor connected via Thunderbolt dock, active desktop.
2. Power the monitor off with its own power button (full hotplug removal).
3. Leave the system awake and idle so outputs enter DPMS-off for several hours
   (overnight). Short off periods (30 s, 5 min) do not reproduce.
4. Power the monitor on and wake the outputs (key/mouse input).
5. Expected: normal picture. Actual: fine grey vertical stripes, unreadable.

## Additional observations

- While striped: `hyprctl monitors` / DRM state report the correct mode and active
  CRTC; screencopy screenshots are clean; DPCD shows HBR3 x4, all lanes locked,
  DSC disabled.
- Cured by DPMS off (all outputs) ~4 s -> DPMS on. NOT cured by replug, dock
  power-cycle, or monitor power-cycle.
- Open discriminator to report back: whether a DPMS cycle of only the external
  output (leaving eDP on) also cures it.
- A/B probes to report back: `amdgpu.dcdebugmask=0x800` (DC_DISABLE_IPS) and
  `=0x200000` (DC_SKIP_DETECTION_LT) overnight results.
- Kernel is under Secure Boot lockdown (integrity): DTN log / link_settings debugfs
  reads are blocked (`Operation not permitted`); `/sys/kernel/debug/dri/1/state` and
  `amdgpu_firmware_info` are readable and attached. Happy to test patches (own MOK
  key enrolled) or run a debug kernel.

## Attached files

- dmesg from boot through reproduction (kernel log covering the overnight window)
- DRM atomic state while striped and after cure (`/sys/kernel/debug/dri/1/state`)
- DPCD snapshots while striped and after cure
- EDID of the external monitor
- Photo of the striped panel
