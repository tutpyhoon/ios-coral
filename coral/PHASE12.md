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

## Confirmed extracted DMG integrity and macOS format recognition — 2026-10-21

Owner ran `coral/probe_macos_images.py ~/Coral-iOS-16-images` and reported:

- `os.dmg` size 4,730,814,044 bytes; **SHA256 OK**, `file`: lzfse/lzvn encoded, `hdiutil imageinfo`: `ULFO` supported.
- `systemos.dmg` size 2,743,074,816 bytes; **SHA256 OK**, APFS, `hdiutil imageinfo`: `UDRW` supported.
- `appos.dmg` size 10,485,760 bytes; **SHA256 OK**, APFS, `hdiutil imageinfo`: `UDRW` supported.
- `images_usable_on_macos: true` indicates recognized container format, **not** actual mounted-file readability.

New tool `coral/inspect_mounted_ipsw.py` (unit-tested, no real image
in GitHub) temporarily invokes `hdiutil attach -readonly -nobrowse
-noautoopen -plist` for each image; lists mount points and relevant
system file paths; always tries `hdiutil detach /dev/diskN` for the
disk reported by that invocation. It does not copy iOS binaries or
write to macOS source images or the Pixel's partitions. If a container
has no mount point or attach fails, report the error and investigate
Linux `apfs-fuse` instead. Do not `sudo` the probe.

```sh
cd ~/ios-coral-phase12
git pull --ff-only origin coral-phase12-springboard
python3 coral/inspect_mounted_ipsw.py ~/Coral-iOS-16-images
```

Potential finding: OS `sbin/launchd`/BackBoard/SpringBoard, SystemOS
`dyld_shared_cache_arm64` and `usr/lib/dyld`, AppOS `System/Applications`.
Actual layout must be derived from output rather than assumed.
Some absolute iOS symlink targets do not resolve under macOS `/Volumes`;
the tool reports those links rather than following them into the host.
Never publish proprietary contents to GitHub or public CI.

The host-only script/test run is
https://github.com/tutpyhoon/ios-coral/actions/runs/39716133372
(**passed**). Real Mac mount result is **pending**.

## Owner local macOS mount inspection passed — 2026-10-21

The owner ran `coral/inspect_mounted_ipsw.py` after SHA verification:

- **OS** image `os.dmg` mounted at `/Volumes/SydneyUpdate20H392.D22D221OS`. Found real Apple `/sbin/launchd` (541,600 bytes), `/usr/lib/dyld` (922,912 bytes), `/usr/libexec/backboardd` (1,184,848 bytes), SpringBoard executable (112,960 bytes), and `System/Library/xpc/launchd.plist` (1,456,980 bytes).
- OS `/System/Cryptexes/OS` is a symlink with target `../../private/preboot/Cryptexes/OS` and `private/preboot/Cryptexes/OS` did not exist in the source OS image, as expected before cryptex merge.
- **SystemOS** image `systemos.dmg` mounted. `System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64` exists but is only **393,216 bytes**. Do NOT conclude the entire shared cache is present at that size: audit all companion `.01`, `.02`, symbols etc.
- **AppOS** image `appos.dmg` mounted, with `System/Library` directory; common app locations were absent.
- **Every image** reported `attached_readonly: true`, `mounted: true`, and `detach_success: true`. No phone partition changed.

Added `coral/survey_ios_volumes.py` to walk those source images using metadata-only `os.scandir` while mounted read-only. It estimates uncompressed/allocated bytes, counts hardlinked files once per volume and explicitly inventories actual dyld cache subfiles. It **never copies files** and reuses the scoped attach/detach handling. Synthetic tests passed in [GitHub Actions run 39716837198](https://github.com/tutpyhoon/ios-coral/actions/runs/39716837198).

Use locally:

```sh
cd ~/ios-coral-phase12
git pull --ff-only origin coral-phase12-springboard
python3 coral/survey_ios_volumes.py ~/Coral-iOS-16-images
```

After the cache and volume size survey, plan an **offline HFS+X case-sensitive journaled sparse disk image** using `hdiutil` `-fs JHFS+X` and source-preserving `ditto` with compression disabled for compatibility. This is tentative and requires host disk capacity and permissions checks, not yet implemented or tested. The next actual device blocker is an independently proven **CORAL-specific UFS read driver**: do not flash `userdata` until that milestone passes.


## Owner survey and offline root candidate checkpoint

The user's 2026-10-21 Mac filesystem survey reported 11,304,857,126
apparent bytes across OS (7,937,213,671), SystemOS (3,359,797,050)
and AppOS (7,846,405); all source image mounts detached. The SystemOS
cryptex has 44 dyld shared-cache members totaling 3,330,359,296 bytes.
There were no inaccessible directories.

An optional, host-local sparse HFS+ root candidate builder is in
`coral/build_ios_hfs_candidate.py`. Its default is plan-only. The
macOS small-image smoke test and synthetic guard tests passed. No full
iOS root has been created or run on Pixel 4 XL yet, and CORAL UFS
read support is not established.
