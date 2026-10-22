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
