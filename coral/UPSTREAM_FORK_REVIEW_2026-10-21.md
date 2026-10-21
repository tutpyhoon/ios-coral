# Cross-fork research for CORAL — 2026-10-21

## Verified baseline (phone)

The Google Pixel 4 XL / coral user video showed XNU kernel boot, then
Phase 09 launching a static arm64 PID 1 on md0 RAM root with multiple
"SWEET init: still alive" heartbeats. This is NOT Apple iOS userspace.
Phase 10 HFS RAM root image passed host checks but has NOT yet been
tested on the phone. Do not flash/wipe partitions.

## Newly updated repositories examined on 2026-10-21

The GitHub commit histories were read directly; commit messages/claims are
not independent proof of the features on Pixel 4 XL.

- lg rachov: https://github.com/lgrachov/ios-sweet
  - 0086 busy-IOService sampler at d143bcf9cf
  - 0087 NO_KEXTD-style IOKit daemon gating at b4fef1b45b
  - 0088 IONetworkStack publication at 0ccb3b6ed6
  - Potential CORAL use: startup/configd diagnosis once real iOS
    userland and kernel networking are brought up. Not needed for HFS Phase 10.
- edadras: https://github.com/edadras/ios-sweet
  - Interactive QEMU framebuffer / QMP harness at 86d06464ba
  - QEMU process sampler at b4150e03a0 (depends on virtio block driver)
  - Potential CORAL use NOW: host-side kernel+HFS QEMU validation.
    The Ginkgo QMP input driver is NOT directly compatible with CORAL's
    minimal storage-free XNU and has NOT been imported.
- xNekom: https://github.com/xNekom/ios-mondrian
  - Framebuffer alias installation fix at dd2c96abee
  - Potential use: if a later kernel loses early-console output. CORAL's
    current physical XNU boot already drew kernel logs, so no blind merge.
- tomaswarner: https://github.com/tomaswarner/ios-dm3q
  - SweetMetal Metal / IOSurface source and IOAcceleratorES nub,
    commits d771b67f1f, 72b03534d3.
  - This runs on a Samsung dm3q Snapdragon 8 Gen 2. Do NOT assume the
    Pixel 4 XL Adreno 640 can run dm3q's Vulkan/Metal backend.
  - Long-term graphics/userland research, not Phase 10.
- Angelpro09xd: https://github.com/Angelpro09xd/ios-sapphire
  - Source for GPU-mediated framebuffer copies at e5c3a678f9,
    different chipset/Adreno 610. Later research only.
- IXackerr: https://github.com/IXackerr/ios-apollo
  - Eight-core startup at 4f1f4c8093, SM8250 virtual timer INTID 27.
  - CORAL measured INTID 19 and boots 1 CPU; do NOT blindly copy
    interrupt priorities or timer INTIDs.
- dipa-studio: https://github.com/dipa-studio/ios-sweet
  - 1664d638df: add reserved panic log region to ADT to avoid
    hangs on some kernels. CORAL's proven early minimal XNU already
    passed boot; changing its memory map now would add unnecessary risk.
- stossy11: https://github.com/stossy11/ios-sweet
  - New Metroid-specific framebuffer/virtual serial changes, commit
    9a7f678fd4, not CORAL's current framebuffer path.

## Implemented without changing Phase 10 image

`coral-fork-research-qemu` branch adds:
- `coral/qemu_coral.py`: adapt the pinned Flame QEMU simulator's
  extracted framebuffer and boot_args geometry to CORAL 1440x3040,
  stride 5760, instead of 1080x2280.
- `.github/workflows/coral-qemu-hfs.yml`: read-only download of the
  proven SHA-pinned CORAL kernel and Phase 10 HFS RAM root, then run
  XNU and static file-read PID 1 in a QEMU-only host simulation.
- Result JSON, screen PNG/text, registers and QEMU diagnostics are saved
  as CI artifacts. A pass indicates only simulated kernel+HFS operation,
  NOT a physical device pass or general iOS compatibility.

## Hold points

1. Keep `coral-hfs-ram10` and its physical boot image untouched.
2. Verify QEMU pass/result.json and inspect its framebuffer screenshot.
3. Test current Phase 10 with temporary `fastboot boot` only after
   separate user/device backup and identity checks; never flash/format.
4. If Phase 10 reaches `FLAME HFS: file read verified`, plan RAM-only
   iOS userland loader/dependency work. Bring in IOKit sampler fixes if
   actual configd or IOService wait evidence warrants them.
5. Do not make GPU, UFS, or multi-core changes before basic RAM-HFS
   behavior is proven on CORAL.

