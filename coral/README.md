# CORAL: toward the iOS 16 home screen on Pixel 4 XL

Target: **Google Pixel 4 XL (coral, Snapdragon 855 / SM8150, 1440×3040)**.
This directory does not contain a booted iOS build. XNU compilation on the
existing `coral-phase22-ci` branch has passed; physical CORAL kernel execution
has **not** been demonstrated.

## What this branch adds

A separate first-device-test route adapted from the Pixel 4 (`flame`) work at
[dimasmds/ios-flame](https://github.com/dimasmds/ios-flame).
The builder checks out exactly
`b91463ab1ef083f81f6c3393593385aa996ceaf0` and fails on unexpected
source differences. It changes the Pixel framebuffer *geometry* from
1080×2280 to 1440×3040 and changes the experimental boot-image identity.
It deliberately preserves all live-FDT splash reservation, memory bounds and
bootloader checks. The boards share the public SM8150 boot-source family,
but this is **not** proof the Pixel 4 XL bootloader or live DT accepts the image.

GitHub Actions builds **two images**:

- `coral-probe-01.img`: read CPU/boot DT information, show it on the
  bootloader's reserved framebuffer if possible, then request a normal reset.
- `coral-probe-02.img`: additionally inspect the proposed 1 GiB XNU RAM
  allocation using DT metadata only. No RAM candidate is touched or reserved
  by this diagnostic.

Both are diagnostics. They do **not** contain XNU, iOS, SpringBoard, a storage
driver or an iOS root image. They issue no UFS media operations or persistent
partition writes. Pixel 4 XL's command-mode screen may remain black until a
display refresh is implemented. A `fastboot boot` success line only confirms
that the bootloader accepted the image, not that the diagnostic ran.

## Where to get the output

Go to the [CORAL temporary boot probes workflow](https://github.com/tutpyhoon/ios-coral/actions/workflows/coral-probes.yml),
choose branch `coral-home-screen`, and open the successful run. Its
`coral-safe-probes` artifact includes both `.img` files and
`manifest.json` with SHA-256 hashes. **Only proceed if the build/host checks
pass and the hashes match**.

For a local Linux build with Python 3, Git, a C compiler, AArch64 GCC/binutils,
ripgrep and liblz4 available:

```bash
python3 coral/build_probes.py
```

This downloads pinned public Google tooling/DTBs via the upstream script.
Generated sources/images are ignored under `coral/_flame_source/` and
`coral/out/`. Remove the generated source directory before rebuilding.
There is no need to push these images to GitHub.

## First hardware test (only an already-unlocked Pixel 4 XL)

**Do not unlock the bootloader just for this test: unlocking erases Android
data.** Make a full backup first. Check that your phone is `coral` before
using any file:

```bash
adb shell getprop ro.product.device   # Must report coral
adb reboot bootloader
fastboot getvar product
fastboot boot coral-probe-01.img
```

`fastboot boot` temporarily loads the image; **never substitute `fastboot
flash`**. The probe waits up to 120 seconds before asking the firmware to
reset. Photograph the screen (even if it shows partial text or a colored
background); note whether Android returns. A black screen is inconclusive.

Only after probe 01 has visibly completed:

```bash
fastboot boot coral-probe-02.img
```

Photograph the RAM-map summary. In particular, `IN RAM`, `CONFLICTS`,
`MAP ERRORS` and `UNBOUNDED POOLS` determine if the candidate can even be
tested. Do **not** try to run the existing CORAL kernel merely because the
two host tests passed.

## Actual path to the home screen

1. Verify the Pixel 4 XL stock boot protocol, live memory map and display
   output with the temporary diagnostics.
2. Adapt the source-built CORAL kernel's early console/boot-CPU path to
   the **validated** Pixel framebuffer/memory map; test with a RAM-only
   source-built PID 1, following Flame's staged kernel handoff.
3. Verify read-only UFS media access, correct LUN and GPT geometry, and
   prevent the inherited Redmi driver from touching persistent storage.
4. Prepare the Apple iPhone X iOS 16 userspace separately, then validate the
   kernel-to-userland boot, HFS+ root, launchd, backboardd and SpringBoard.
   Destructive iOS installation would require explicit approval and backups.

**Current checkpoint:** source-built CORAL kernel compiles; hardware stages
1–4 are not yet proven. Do not run Redmi `shim/build.sh` / `mkadt.py` with
hardcoded SWEET addresses on a Pixel 4 XL. The original upstream instructions
for formatting userdata are **not** valid for CORAL.
