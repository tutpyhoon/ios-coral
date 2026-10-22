# CORAL phase 10 handoff — 2026-10-20 local (2026-10-21 UTC)

Target: Google Pixel 4 XL (coral / SM8150), iOS/XNU 16 research port.

## Physical evidence

- Probes 01–04: user photographed and confirmed runtime memory-map/two-page/MMU checks and Android recovery. No guarantee of ownership for the entire proposed 1 GiB.
- Preflight 07: user photographed `RUNTIME CHECKS AND PAYLOAD PASS` and confirmed normal restart into Android.
- First XNU entry 08: user provided a video showing XNU CPU0, timer, zone/VM, BSD and IOKit initialization through an IOMedia/Apple_HFS root wait. The kernel had **no root filesystem**. The user restarted the device manually, not automatically. No evidence that the full iOS userland ran.
- RAM-only Phase 09: user provided `IMG_0059.mov`, showing `Added memory device md0/ram0`, `BSD root: md0`, `load_init_program: attempting to load /sbin/launchd`, the static test `*** SWEET userspace: init running as PID 1 ***`, and repeated `SWEET init: still alive` heartbeats. This demonstrates kernel/userspace transition and RAM-root process execution. The static test is not Apple launchd.
- The photographs/videos reside in the conversation, **not** this public GitHub repository.

## Current working branches/artifacts

- Phase 05 pinned XNU reference kernel source SHA: `1b191cb58250d0705d8a51287127505aa4bc0789`. Built kernel SHA-256: `2946d4dda4ae46a794f945e9e3d26a147359d295a371f22e02474206a33e83d4`.
- `coral-xnu-first-entry` — CI run 39542383177 (passed); first XNU boot proven in user video.
- `coral-ram-init09` — CI run 39544476480 (passed); hardware PID 1 and two heartbeats proven by user video.
- `coral-hfs-ram10` — CI run **39546203266 (passed)**; new experimental `coral-phase10-hfs-ram-UNTESTED` artifact. **Confirmed on CORAL hardware by owner's text report on 2026-10-21.**
- Phase 10 CI builds a 16 MiB HFS+ volume with a static, ad-hoc signed arm64 file-reading process as `/sbin/launchd`, `/etc/flame-test`, and `/dev`. It embeds the volume in the same proven minimal XNU as `rd=md0`. The expected new result is `FLAME HFS: file read verified` and repeating `SWEET init: still alive`. Upstream `FLAME` text in the test program is intentional.

## Safety and engineering limits

- Only a temporary `fastboot boot` image may be considered for a backed-up, already-unlocked Pixel 4 XL after checking file SHA256SUMS and `fastboot getvar product` = `coral`. No flash/format/wipe request.
- XNU execution may hang or panic. Successful PID 1 does not automatically restart; use the device hardware controls to force restart after capturing.
- Phase 10 must not access UFS or persistent storage; no root partition modification or iOS install is in the build.
- Candidate high RAM is not exhaustively characterized and framebuffer stride (5760) is inferred rather than independently measured.
- Even Phase 10 success means only an HFS+ read from RAM: **it does not mean iOS launchd, dyld, SpringBoard, or the iOS home screen works**.

## Physical Phase 10 result (2026-10-21)

After temporarily booting the Phase 10 image, the owner replied **"yes those lines showed up"** to the expected output:

- `FLAME HFS: file read verified`
- `SWEET init: still alive`

Record as **owner-reported physical test passed**. This turn contains no separately supplied Phase 10 video or machine-readable console log, so we should not claim independent visual verification, heartbeat count, or that Android recovery was confirmed afterward.

## Next milestone — Phase 11 planning

Develop a **RAM-only userspace dependency test** before replacing the static test `/sbin/launchd` with Apple's dynamic program. Verify Mach-O exec of a second userspace process, launchd/dyld/shared-cache dependencies, code-signature and ABI handling, RAM budget and filesystem layout. iOS dyld/launchd are proprietary assets that must come from properly obtained user-owned Apple firmware; do not upload or redistribute them in CI. Keep the known-working Phase 10 image and no-storage policy unchanged until a separately validated test exists. Do not mistake the successful synthetic PID 1 for real iOS userland.
