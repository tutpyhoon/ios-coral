# Coral adoption of NWylynko/ios-flame (2026-10-22)

This branch is a **non-bootable, host-only adaptation workstream**, kept
separate from the earlier verified Coral temporary boot probes and the
Mac-local HFS+ iOS root candidate.

**Why change strategy:** [NWylynko/ios-flame](https://github.com/NWylynko/ios-flame)
reports running iOS 16.7.16 (20H392) with real launchd, SpringBoard, UFS,
USB, touch, and Adreno 640 Metal acceleration on the Google Pixel 4
(`flame`). It has a complete 0001–0124 XNU patch series plus shim,
Turnip, and SweetMetal2 code, unlike our Phase 11 minimal XNU test.
Its README explicitly says **Pixel 4 XL (`coral`) is untested**.
The README/engineering logs are project-authored reports, not independent
verification on our Pixel 4 XL.

## Source

- Upstream: `https://github.com/NWylynko/ios-flame`
- Pinned SHA: `745c4341af86089efb0df851fa8a27fb8face624`
- Ancestor: `dipa-studio/ios-sweet`.
- Root userland: iPhone X iOS 16.7.16 build `20H392`; Apple/Google firmware
  is **not in Git**, and must remain on the owner's Mac.
- Licensing: repo states MIT for additions; XNU changes APSL 2.0;
  Metal/Turnip source and dependencies carry their original licenses.
  Preserve LICENSE and CREDITS and third-party notices.

## Why cannot flash the flame image on coral

The Snapdragon 855 (SM8150) and Adreno 640 are shared, so much of the
XNU UFS/Apple-userspace/Turnip pipeline should transfer. But:
- **Flame native panel:** 1080 x 2280, 4320-byte framebuffer stride.
- **Coral native panel (measured):** 1440 x 3040, 5760-byte stride,
  framebuffer physical address 0x9c400000, reserved 0x02400000.
- Both share an aspect ratio, but the output frame and display controller
  programming differ; same Adreno GPU does not imply identical DPU state.
- The Flame GPU present patch `0095` hardcodes `PANEL_W=1080`,
  `PANEL_H=2280`, a ~10 MiB GPU framebuffer mapping, and 4352-byte
  GPU panel pitch. Coral needs ~17.5 MiB of uncompressed display pixels,
  so this mapping is insufficient until reworked and checked.
- XNU early framebuffer constants in `0083` hardcode 1080/2280/4320.
- Touch, PMIC GPIO/keys, stock boot DTB/DTBO, reserved memory,
  GPU firmware loading, high-memory allocations and panel init must
  be verified against **live Coral hardware**. Do not transplant Flame's
  TWRP/factory images or literal userdata partition offsets.

## Started

`coral/prepare_upstream_flame.py` consumes a **fresh clone** of the
exact pinned upstream commit and changes only the offline
`tools/mkadt.py` source to use Coral's known framebuffer
geometry/identity. It validates the upstream patch inventory and emits
`coral-flame-port-report.json` explicitly marking unported drivers.
No phone image is emitted. GitHub CI:
[Coral Flame port preflight](https://github.com/tutpyhoon/ios-coral/actions/runs/39866922004)
**PASSED**.

## Actual shortest development path

1. Port the Flame boot shim/ADT to Coral using the previously
   hardware-verified Pixel 4 XL FDT and framebuffer profile, and preserve
   a small temporary XNU diagnostic. **No partition flashing.**
2. Rebuild pinned full 0124 XNU patch stack on a fresh tree with
   device-specific display and memory changes applied at the right stage.
   Do **not** mix late Flame GPU patches into Phase 11's 0001–0027-only
   code: they depend on the other upstream files.
3. Start with an **isolated Coral framebuffer present test** using the
   full 1440×3040 mapping; retain watchdog and fastboot recovery.
   Confirm pixel order, pitches, page mappings, DSC/panel autorefresh
   before enabling Metal or touching iOS root storage.
4. Connect the UFS block path already proven on owner hardware,
   verify GPT partition mapping, then independently inspect the
   local, merged HFS+ root. Do not assume a Mac `.sparseimage`
   can simply be written as a raw `userdata` partition.
5. Only with backups, matching root geometry and explicit separate
   consent for partition replacement, deploy a *Coral-specific* iOS
   HFS+ root image, then debug Apple launchd/BackBoard/SpringBoard
   and the Turnip/Metal userland from upstream.

### Hardware evidence from earlier Coral probes

- Actual XNU RAM HFS+ PID1 `fork/exec/wait4` passed on device.
- Real UFS LUN0 `READ(10)` succeeded with the GPT signature
  `0x45464920 0x50415254` and 4096-byte physical blocks.
- This is **not yet proof** that the entire upstream full XNU and GPU
  driver will run on Coral, or that a real Apple userspace has booted.

**Recovery:** all new experiments must initially use checksum-verified
`fastboot boot`. No copied Flame boot image, `fastboot flash`, partition
erase, TWRP writes or `dd` to Coral userdata at this stage.

## Executed full Flame build work — 2026-10-22

The source adaptation is **now compiling real upstream full code**, not merely the old PID1 test:

- `coral/port_flame_full_xnu.py`: after applying ALL upstream Flame XNU patches 0001–0124, guarded edits change the boot framebuffer to 1440×3040/5760, touch dimensions to 1440×3040, GPU output panel W/H to 1440×3040, GPU scanout pitch to 5760 bytes, and Adreno 640 framebuffer mapping from 10 MiB to **18 MiB** (rounding a 17,510,400-byte panel up to 2 MiB blocks). **This is a compilation overlay, not proof the Pixel 4 XL DPU/panel works.**
- [Full Flame XNU 0124 compilation job](https://github.com/tutpyhoon/ios-coral/actions/runs/39869118799): exact upstream commit `745c4341af86089efb0df851fa8a27fb8face624` and pinned blacktop build revision `663906528d1cd5ea8fde7de6f16de73db9511549`. Source/input validation passed. Mac build is independent of the owner's phone.
- `coral/port_flame_shim.py`: adapts the shim console to 1440×3040; critically **disables Flame's UFS scratch/rescue logging** (which otherwise writes fixed userdata LBAs) and the Flame-specific panel autorefresh call on the normal path. This deliberately disables those features for the initial Coral tests.
- [Shim source compilation job](https://github.com/tutpyhoon/ios-coral/actions/runs/39869658682): **SUCCESS**. Artifact `coral-flame-shim-elf-HOST-ONLY` is a raw linked ARM64 ELF, **not** a flashable boot image; it lacks the owner's Coral boot DTB, correct Apple device-tree boot payload and safe hardware run validation.
- [ADT source preflight](https://github.com/tutpyhoon/ios-coral/actions/runs/39866922004): **SUCCESS** for known Coral 1440×3040 framebuffer and `google,coral` identity, but no physical boot.

Do **not** run the upstream Flame `flame-run.sh`, `dd of=/dev/block/sda15`, TWRP or `flash-all.sh` on the Pixel 4 XL. The regular Flame shim and XNU include storage-write paths; our future Coral bring-up must explicitly gate those and use a local stock `coral` DTB, not `flame` stock/dtb. No userdata replacement is performed by the above GitHub jobs.

## Verified build results — 2026-10-22

- **Full upstream XNU 0124 + Coral framebuffer/GPU geometry: SUCCESS.** [GitHub Actions run 39869118799](https://github.com/tutpyhoon/ios-coral/actions/runs/39869118799). Both source-gating and Mac XNU compilation jobs passed. The output `kernel.development.sweet` is a **17,890,776-byte ARM64 Mach-O executable**, build `DEVELOPMENT_ARM64_SWEET`. Artifact: `coral-flame-full-xnu0124-UNTESTED`, includes `SHA256SUMS` and is valid only as a raw kernel engineering input, NOT `fastboot boot` format.
- **Coral safe shim: SUCCESS.** [GitHub Actions run 39869658682](https://github.com/tutpyhoon/ios-coral/actions/runs/39869658682), artifact `coral-flame-shim-elf-HOST-ONLY`. It linked into an AArch64 ELF with `ufs_ok=0` and the normal Flame DPU-autorefresh call removed; no stock `coral` boot DTB was bundled.
- ADT adaptation preflight passed in run `39866922004` but the **full boot chain has not been tested**. Both artifacts are downloaded from GitHub Actions, not auto-deployed onto the owner's phone.
- No real Apple `launchd`, SpringBoard or Turnip renderer has executed on `coral` in these build jobs. The author's actual GPU success remains demonstrated on the smaller `flame`, not this 4 XL.
- Next: combine the verified Coral shim, the raw kernel, a read-only RAM root and stock Coral DTB into an isolated **temporary boot** test; first validate XNU start, memory carveouts and panel while deliberately NOT enabling Flame UFS userdata writes or GPU register programming. Do not flash.


## 2026-10-22/23 follow-through: first FULL Coral XNU + storage write fences COMPILED

- **Full upstream XNU 0124 with Coral 1440×3040/5760 panel constants and
  18 MiB GPU framebuffer mapping:** GitHub compilation **PASS**,
  [run 39869118799](https://github.com/tutpyhoon/ios-coral/actions/runs/39869118799).
- **Follow-up compile with three independent UFS write barriers:**
  **PASS**, [run 39876050024](https://github.com/tutpyhoon/ios-coral/actions/runs/39876050024).
  The raw kernel Mach-O `kernel.development.sweet` was compiled.
  Source `coral/port_flame_full_xnu.py` blocks write-direction SCSI command
  submission, returns EROFS from WRITE(10), and overrides `su.writable` to
  false despite any `ufsrw=1` boot arg. GitHub verified all three
  fences in patched source. This is a **temporary testing build only**.
- **Coral boot shim ELF** built at
  [run 39869658682](https://github.com/tutpyhoon/ios-coral/actions/runs/39869658682).
  The normal path disables upstream Flame's scratch/rescue UFS writes
  and its DPU autorefresh register sequence, and uses Coral FB dimensions.
  It remains an ELF, not a flashable image.
- **Previously hardware-proven Phase11 boot image v2 header/FDT audit:**
  [run 39876765794](https://github.com/tutpyhoon/ios-coral/actions/runs/39876765794)
  PASS. Header version 2, 4096-byte pages, `dtb_addr=0x1f00000`,
  embedded DTB 1,048,284 bytes, first FDT length 525,221 bytes, SHA256
  `f582348d19807e8f4681e6c226c9947ef64a380ef1c85c487458f7bf085b89da`.
  **This does not verify the actual DTB's selected Coral panel revision**.
- **QEMU synthetic memory-only start**:
  [run 39876331421](https://github.com/tutpyhoon/ios-coral/actions/runs/39876331421)
  uses the first full kernel, and
  [run 39876999404](https://github.com/tutpyhoon/ios-coral/actions/runs/39876999404)
  uses the write-fenced full kernel plus the previously tested 16 MiB HFS
  RAM root with two static user processes. These are **host-only**, and
  results must be checked before claiming any new boot success.

**Important:** the full XNU/GPU source is now compiling, but **SpringBoard
is not running on physical Coral**. The Pixel 4 project's public success
does not establish compatible Coral DPU registers, touch, firmware,
reserved RAM or file-backed root. No full Coral Android boot image has
yet been published; no UFS partitions have been touched.
