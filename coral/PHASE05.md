# CORAL Phase 05 — gated XNU handoff (preparation only)

**Device:** Google Pixel 4 XL (`coral`, Qualcomm SM8150). **Goal:** execute the source-built XNU kernel with a RAM-only diagnostic, without altering Android partitions. **Status:** NOT BOOT-READY; no Phase 05 image has been produced.

## Hardware evidence (device photographs, 2026-10-20)

- Probe 01 displayed output on the physical Pixel 4 XL. Observed: EL1; MIDR `0x51DF805E`; MPIDR `0x81000000`; TGRAN16 field `1` (16 KiB supported); timer frequency 19,200,000 Hz; PSCI `0x00010001` (v1.1); FDT at `0x84500000` with `0xACB47` bytes; splash reservation `[0x9c400000, 0x9e800000)` (36 MiB); RAM banks `[0x80000000, 0xbcc00000)` and `[0xc0000000, 0x200000000)`. Display text was visible on the Pixel 4 XL. The probe's contiguous pixel row layout works for diagnostics but does not independently establish physical display stride.
- Probe 02 reported candidate RAM `[0x100000000, 0x140000000)` (1 GiB), `IN RAM=1`, `RAM BANKS=2`, `FIXED RANGES=0x1a`, `DYNAMIC POOLS=8`, `UNBOUNDED POOLS=0`, `CONFLICTS=0`, `MAP ERRORS=0`; it did **not** touch the candidate RAM.
- Probe 03 read/modified/restored the first `0x4000` bytes at `0x100000000` and last `0x4000` bytes at `0x13fffc000`. Pattern and restoration errors were both zero. **The rest of the 1 GiB window was not tested.**
- Probe 04 enabled a temporary 16 KiB MMU mapping, verified first/last translations, repeated the two-page test with zero errors, restored SCTLR, and disabled MMU.
- User confirmed that Android restarted normally after Probe 02, 03 and 04. The four probe images were all booted temporarily with `fastboot boot`; no partition flash was requested.

These tests support a limited boot-environment claim. They **do not** prove that the full RAM range is unowned, that firmware mappings remain safe after XNU reconfigures MMU/GIC, or that a Coral kernel is ready to boot.

The measured values and host-side **consistency-only** checks are recorded in [hardware_observations.json](hardware_observations.json) and [check_hardware.py](check_hardware.py). The checker must **not** be interpreted as approval to boot a kernel; every critical value needs a live preflight check before copying a payload.

## Repository artifacts

- [Successful CORAL XNU CI run](https://github.com/tutpyhoon/ios-coral/actions/runs/39371450369), branch `coral-phase22-ci`, compiled the `CORAL` machine config. The `xnu-kernel` artifact exists. A successful CI compile is not proof of hardware compatibility.
- The `coral-home-screen` branch contains the **01–04** temporary probes in `coral/build_probes.py` and documents the read-only/hardware-gated policy.
- **Do not use** `shim/build.sh`, `tools/mkadt.py`, `tools/mkpayload.py` unchanged with `CORAL`. Their SWEET hardware assumptions are not a suitable Coral boot contract.
- Upstream Pixel 4 (`flame`) source has a bounded, storage-free early-console loader and a separate minimal XNU patch profile, but hardcodes `1080x2280`, 4320-byte stride and a `google,flame` ADT. Merely changing the probe dimensions does not adapt the loader or kernel.

## Phase 05 implementation requirements

1. **Source profile, no storage:** construct a separately audited `CORAL` early-console XNU configuration from the common early open-source patches plus the Coral machine support; exclude UFS/media write paths, persistent logs, mounting Android partitions, unnecessary SWEET device drivers, and iOS rootfs. Do not boot the full Phase 22 kernel artifact without this audit.
2. **Boot protocol and ownership:** compare the actual Coral boot image/FDT, probe 01 CPU features, PSCI method, GIC timer interrupt, and live ABL reservation map. Hard-fail if runtime geometry, CPU exception level, RAM bounds, page size or bootloader-provided DT disagree.
3. **Memory and framebuffer:** candidate memory is `0x100000000–0x13fffffff`; loader must bound-check the full embedded image and kernel sections against RAM and boot reservations. The **probe** uses 1440×3040 pixels and writes via a contiguous 1440-pixel row. XNU loader and early console must use a separately confirmed **stride**; `1440*4=5760` bytes is an unverified candidate, not a live stride measurement. Splash reservation is nominally `0x9c400000`, but do not infer from this alone that all XNU mappings are correct.
4. **ADT and kernel entry:** use `google,coral`, one boot CPU, the validated virtual timer/GIC interface, 16 KiB page granule, correct boot-args ABI and board-specific framebuffer. Check the linked Mach-O, page-table alignment, loaded segment bounds, and source/output hashes on the host. Halt on mismatches.
5. **First executable handoff:** produce a separate, temporary `fastboot boot`-only test image **only after** the above checks pass. Print early console marks/exception state and attempt a RAM-only PID 1 later; never package an Android-storage-writing kernel into this boot image.
6. **Further stages:** demonstrate XNU early entry and boot CPU/timer/console first; then RAM-only userspace; **only later** consider read-only UFS and iPhone X iOS userspace. There is no legitimate basis to promise a home-screen boot date yet.

## Stop rules

- **No `fastboot flash`, partition formatting, or writing userdata** in Phase 05.
- Do not request booting the current Phase 22 kernel artifact on Coral.
- If any runtime check fails, leave the existing Android installation alone and return to diagnostics.
- Bootloader hangs or a forced reset remain possible even with `fastboot boot`. Recoverability is not guaranteed.

**Next engineering deliverable:** a reviewed, storage-free Coral kernel/ADT/loader source profile with CI and host-level tests. Only once a bootable artifact exists should instructions for a device test be issued.
