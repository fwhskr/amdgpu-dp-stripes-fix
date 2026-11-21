#!/bin/bash
# Capture display evidence while the external screen is STRIPED.
# Run BEFORE any DPMS cycle / replug. Read-only; safe anytime.
# Usage: stripes-capture.sh [label]
set -u
TS=$(date +%Y%m%d-%H%M%S)
LABEL=${1:-striped}
OUT=/tmp/opencode/stripes-evidence-$TS-$LABEL
mkdir -p "$OUT"
echo "capturing to $OUT"

{ date -Is; uname -r; cat /proc/cmdline; } > "$OUT/system.txt" 2>&1
hyprctl monitors all > "$OUT/hyprctl-monitors.txt" 2>&1
hyprctl monitors -j  > "$OUT/hyprctl-monitors.json" 2>&1
sudo -n cat /sys/kernel/debug/dri/1/state > "$OUT/drm-state.txt" 2>&1
for c in /sys/class/drm/card1-*/; do
  n=$(basename "$c")
  { echo "== $n"; cat "$c/status" 2>/dev/null; cat "$c/dpms" 2>/dev/null; cat "$c/modes" 2>/dev/null; } >> "$OUT/drm-sysfs.txt"
done
cp /sys/class/drm/card1-DP-4/edid "$OUT/dp4-edid.bin" 2>/dev/null
sudo -n journalctl -k --no-pager -o short-iso --since "-12h" > "$OUT/kernel-12h.log" 2>&1
grep -iE 'amdgpu|drm|thunderbolt|HPD|DMUB' "$OUT/kernel-12h.log" > "$OUT/kernel-drm.log" 2>&1
tail -n 2000 "$XDG_RUNTIME_DIR"/hypr/*/hyprland.log > "$OUT/hyprland-tail.log" 2>&1
journalctl --user -u hypr-dp4-guard --no-pager -n 50 > "$OUT/guard.log" 2>&1

# DPCD snapshot of every DP aux channel that answers
python3 - "$OUT" <<'PYEOF'
import subprocess, json, sys, glob
out = sys.argv[1]
for dev in sorted(glob.glob('/dev/drm_dp_aux*')):
    def rd(off, n):
        r = subprocess.run(['sudo','-n','dd',f'if={dev}','bs=1',f'skip={off}',f'count={n}'],
                           capture_output=True)
        return r.stdout if len(r.stdout) == n else b''
    hdr = rd(0, 16)
    if not hdr or hdr == bytes(16):
        continue
    cfg, st = rd(0x100, 8), rd(0x200, 16)
    snap = {'dev': dev, 'dpcd_rev': hex(hdr[0]), 'max_rate_reg': hex(hdr[1]),
            'max_lanes': hdr[2] & 31, 'bw_set': hex(cfg[0]) if cfg else None,
            'lanes_set': (cfg[1] & 31) if len(cfg) > 1 else None,
            'lane01_status': hex(st[2]) if len(st) > 2 else None,
            'lane23_status': hex(st[3]) if len(st) > 3 else None,
            'adjust_req': st[6:8].hex() if len(st) > 7 else None,
            'dsc_enable_0x160': rd(0x160, 4).hex()}
    name = dev.split('/')[-1]
    json.dump(snap, open(f'{out}/dpcd-{name}.json', 'w'), indent=1)
    print(name, snap)
PYEOF

grim -o DP-4 "$OUT/dp4-framebuffer.png" 2>/dev/null
echo "done: $OUT"
ls -l "$OUT"
