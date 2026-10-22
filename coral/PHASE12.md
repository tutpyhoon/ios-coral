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
