# Next real Coral hardware gate — Full XNU UFS GPT probe

**Current state:** [Build 39891811910](https://github.com/tutpyhoon/ios-coral/actions/runs/39891811910)
has passed and provides
`coral-full-flame-UFS-GPT-DIAG-UNTESTED`. This is the whole
Flame-based XNU, adapted to the 1440×3040 Pixel 4 XL screen, with the
source-built Phase 11 HFS+ RAM root. It **does not** include Apple
launchd or SpringBoard. The boot image is **not yet hardware-tested**.

## Why this is the next test

The user already photographed successful bare-metal direct UFS GPT
reads using a standalone diagnostic. This new image instead asks the
real XNU `sweet_ufs` driver to enumerate the actual GPT `userdata`
partition, while retaining the known RAM-root PID1. It isolates the
remaining *kernel-integration* risk without erasing Android user data.

**What it changes:** temporary fastboot boot, Qualcomm UFS host
controller queue registers, and device-to-memory DMA.

**What it does not change:** internal UFS partition contents; flashable
boot slots; firmware; A/B or GPT partition tables. The compiled
kernel has three unconditional UFS WRITE command fences.

## On the Mac

Use an existing clean `coral-flame-port` checkout or clone:

```bash
git clone -b coral-flame-port --single-branch \
  https://github.com/tutpyhoon/ios-coral.git \
  "$HOME/ios-coral-flame"
cd "$HOME/ios-coral-flame"

# Non-destructive plan:
python3 coral/test_full_xnu_ufs.py --run-id 39891811910

# Hardware attempt (only after verifying backups and recovery route):
python3 coral/test_full_xnu_ufs.py \
  --run-id 39891811910 \
  --execute \
  --confirm BOOT_CORAL_UFS_DIAG
```

Requires authenticated GitHub CLI (`gh auth status`), `adb`,
`fastboot`, unlocked Pixel 4 XL and a recovery method. The launcher
validates all SHA256 values and checks `fastboot getvar product` for
`coral`. The sole device operation is `fastboot boot`, not
`fastboot flash`. It may hang or reboot; no restoration is guaranteed
from an unsupported image.

## Expected evidence

Photograph the full screen. The ideal markers are:

```text
CORAL UFS DIAG: GPT userdata FOUND, rc=0
CORAL11: PID1 HFS+ root active
CORAL11: child exec succeeded
CORAL11: child exited status 0
```

Partial output, a panic or a black screen are still useful evidence.
A black screen does not prove the storage probe failed.

After physical XNU UFS access works, the next engineering gates are:

1. Validate the full real Apple HFS+ image using the Mac finalizer;
   correct cryptexes, `logd`, keybag and launchd preferences.
2. Compile and separately test the **future userdata-only writable**
   profile (double opt-in: `ufsrw=1` and
   `coraluserdatawrite=1` with `ufsroot=userdata`). The separate
   code is NOT a boot image and is not physically tested.
3. Only with physical proof and an independent recovery copy,
   consider the destructive user-approved `userdata` replacement,
   then test real Apple launchd, BackBoard/SpringBoard, DPU panel
   timing and Adreno 640/Turnip Metal.

**No physical Pixel 4 XL iOS home-screen boot is verified yet.**
