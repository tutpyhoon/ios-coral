# Combined Phase 12: Real iOS Userspace → SpringBoard

**Status:** new development branch, NO real iOS userland executed on the Pixel 4 XL.
Previous milestone: Phase 11 screenshot IMG_0064.jpg demonstrated **XNU + RAM HFS+
mount + fork + execve + wait4 + PID1 heartbeat on real CORAL hardware**.
Photo lives in the conversation, not in this public repository.

## Target

Display the actual iOS 16 SpringBoard home screen on Pixel 4 XL (coral),
even if touch, Wi-Fi, cameras, mobile radio, GPU acceleration and normal
power management do not initially work.

This is one **combined engineering phase** comprising multiple diagnostic
gates. Combining names does **not** eliminate the underlying dependencies
or guarantee the home screen will become bootable.

## Known-good starting point

- Kernel source revision: **1b191cb58250d0705d8a51287127505aa4bc0789**.
- Pinned kernel SHA256: `2946d4dda4ae46a794f945e9e3d26a147359d295a371f22e02474206a33e83d4`.
- `coral-phase11-userland-prep`: CI run `39712670256` passed full synthetic
  fork/exec/wait4 in QEMU and owner provided Pixel 4 XL screen showing the same.
- `coral-hfs-ram10`: prior HFS+ single-process baseline for recovery.
- No real iOS binary has yet been executed by this CORAL kernel.
- Source-built `/sbin/launchd` in phases 09–11 is **not** Apple's launchd.

## Gate A: Offline manifest and dependency audit (no device access)

`python3 coral/ios_root_audit.py /path/to/extracted-ios-root`
should inspect local, user-provided OS/Cryptex/merged root files for:
Mach-O arm64 launchd, dyld linkage, SpringBoard, backboardd, dyld shared cache,
file sizes, symlink targets, and rough RAM feasibility. It MUST NOT
download copyrighted Apple components, upload them, or copy them into
public CI artifacts. This is only structural analysis, NOT iOS execution.

Upstream Redmi SWEET uses a full **~16 GiB HFS+ root in userdata** for
unmodified iPhone X iOS 16.7.16 userland and has custom UFS storage +
software-rendered IOMobileFramebuffer/IOSurface integration. The
current CORAL research window is **1 GiB candidate RAM** that has NOT been
exhaustively validated. Therefore **do not assume a full iOS root can
be embedded in our small 16 MiB RAM root**.
See: https://github.com/dipa-studio/ios-sweet/blob/main/README.md

## Gate B: First dynamically linked child

Build a **separate, non-flash** test variant from the Phase 11 source-built
PID1, using a *locally supplied* dyld and minimal test dynamic Mach-O +
its closure/shared-cache dependencies. First validate in QEMU.
No Apple files in the public GitHub repo; no modified Android partitions.

## Gate C: Actual Apple launchd and core services

Only after dynamic execution works, change test PID 1 to actual launchd
using local legally obtained iOS assets. Debug launch cache, userland
code signing/trust policy, filesystems, IOKit/IORegistry, syscalls,
sandbox expectations, dyld cache and launchctl services.
Do not blindly merge SWEET board-specific patches. Relevant portable
IOKit fixes exist in `lgrachov/ios-sweet`, but must be isolated and
measured against logs.

## Gate D: BackBoard + SpringBoard + basic display

Adapt portable IOMobileFramebuffer/IOSurface/IOHID service layers
and software UI compositing only after Apple system services are up.
CORAL (SDM855/Adreno 640) is **not** Redmi SWEET, Sapphire or DM3Q;
GPU register addresses, IRQs and SMMU mappings are not interchangeable.
The real pixels/home screen are the required end-of-phase evidence.

## Hardware/storage guardrails

- Keep proven Phase 10 and Phase 11 images unchanged.
- Only temporary, model-verified `fastboot boot` for new test probes;
  NO `fastboot flash`, erase, format or userdata replacement.
- No unreviewed UFS controller use or persistent logs.
- Missing or insufficient RAM and proprietary iOS dependencies are
  blockers, not reasons to silently escalate to partition flashing.
- Kernel hangs do not automatically reboot to Android. Full backup,
  device recovery route and precise product check are required before
  any new experimental image is attempted.
- No credential/private file collection in public GitHub Actions.

**Next executable work:** the host-only root dependency audit. Do not
prepare a physical Phase 12 image until the audit identifies the minimum
viable dynamically linked file set.

## Implementation record — 2026-10-21

- **Phase 11 photographed PASS** committed to `coral-phase11-userland-prep` via commit `e10964b088b2090ee384885048ed3950a5cfcf66`. No Phase 11 image changed.
- Phase 12 branch implemented `coral/ios_root_audit.py`: **read-only, local-only** Mach-O audit of launchd/dyld/BackBoard/SpringBoard and the dyld shared cache. It reports dynamic-linker commands and CPU architecture, explicitly does not establish iOS bootability, and has no mount/flash/download functionality.
- Synthetic tests in `coral/tests/test_ios_root_audit.py`: **6 tests passed**, including arm64 Mach-O parsing, a complete synthetic dependency tree, virtual absolute symlink resolution, path-escape rejection, truncated Mach-O rejection and missing-file handling.
- GitHub Actions run [39714171134](https://github.com/tutpyhoon/ios-coral/actions/runs/39714171134): **SUCCESS**. No Apple proprietary binaries uploaded or included.
- **Pending**: local user-provided legitimate iOS 16 merged OS/Cryptex root or path; then dynamic-linker dependency and filesystem budget investigation. No actual iOS launchd/SpringBoard code run on Coral yet.

## Updated owner constraints and IPSW preparation — 2026-10-21

The owner confirmed they already have a downloaded iPhone X IPSW on macOS
and are not concerned about preserving the existing LineageOS installation.
This **allows evaluating a dedicated iOS HFS+ root on userdata**, but does
NOT establish an explicit authorization to flash, erase or overwrite the
device immediately. No destructive command is part of this step.

The iPhone X target is iOS **16.7.16 / 20H392 / D22AP (iPhone10,3)**.
The published firmware file is
`iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw`.
`coral/ipsw_prepare.py` identifies OS, Cryptex1,SystemOS and
Cryptex1,AppOS paths from BuildManifest and optionally extracts their
images on the user's Mac. The tool needs only stdlib `zipfile`,
`plistlib` and SHA-256, leaves the original IPSW unchanged, and rejects
ambiguous/incorrect firmware. It does not construct an HFS+ root.

Run on the **user's Mac**, not in GitHub Actions:

```sh
python3 coral/ipsw_prepare.py "/path/to/iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw"
python3 coral/ipsw_prepare.py "/path/to/iPhone10,3,iPhone10,6_16.7.16_20H392_Restore.ipsw" --extract "$HOME/Coral-iOS-16-images"
```

The resulting `os.dmg`, `systemos.dmg`, `appos.dmg` (names may retain
their original image file extensions) are personal Apple firmware
components: **never commit or upload to public GitHub or public CI**.

**Next engineering blocker**: an original, CORAL-specific (Qualcomm
SM8150/Pixel 4 XL) UFS storage driver that can *read* a dedicated HFS+
root. Upstream SWEET's UFS addresses, clocks, PHY, DT nodes and reset
sequence cannot be adopted unchanged. Build a separate read-only probe
on hardware before any write to userdata. Also verify that the Pixel's
partition arrangement and boot chain permit a safe restore path.
The upstream `tools/mkiosroot.sh` uses `apfs-fuse`/Linux and a
journaled 16 GiB HFS+ image; macOS cannot simply run that shell
script as-is. An appropriate Linux VM or supported extraction tool may
be needed for full root construction.

Until actual CORAL UFS read access and full iOS root validation succeed,
**do not flash userdata**: doing so prematurely would destroy the
Android data volume without giving XNU a bootable root. A later,
separately approved userdata replacement must be accompanied by
backups, a tested stock factory-image restore procedure, and explicit
understanding of the possibility of data loss or an unbootable device.

IPSW manifest preflight synthetic CI: https://github.com/tutpyhoon/ios-coral/actions/runs/39714759134 (passed).

## Observed owner IPSW extraction — 2026-10-21

The owner ran `coral/ipsw_prepare.py` successfully on their Mac:
- iPhone X D22AP, iOS 16.7.16 (20H392), Erase restore identity.
- `os.dmg`: 4,730,814,044 bytes (from `087-86698-044.dmg`).
- `systemos.dmg`: 2,743,074,816 bytes (from `087-86593-047.dmg`).
- `appos.dmg`: 10,485,760 bytes (from `087-86715-047.dmg`).
- All three reported extracted into `~/Coral-iOS-16-images/` on Mac.
- No independent post-extraction digest check or filesystem readability test has been recorded yet. This is NOT a bootable HFS+ merged root.

Next safe local check:

```sh
cd ~/ios-coral-phase12
git pull --ff-only origin coral-phase12-springboard
python3 coral/probe_macos_images.py ~/Coral-iOS-16-images
```

The probe reads the earlier `local-image-report.json`, measures independent
SHA-256 over each of the three DMGs (~7.48 GB total), checks the original
manifest-recorded byte sizes and asks macOS `hdiutil imageinfo` whether
each image's outer container is recognized. It never attaches/mounts
devices or modifies files, and handles unsupported raw APFS/cryptex images
by reporting that limitation.

Treat macOS `hdiutil imageinfo` success as a *format recognition result
only*: it is not evidence that compressed OS/cryptex contents have been
mounted or that a full HFS root can be built natively. The upstream
Linux `apfs-fuse` route remains the fallback. The owner will retain
firmware files locally; do not upload to public GitHub or CI.

No partition flash or wipe has been authorized/performed at this stage.
