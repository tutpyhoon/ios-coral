# Phase 11 — Userspace process and loader bring-up (planning only)

Status: **BUILT and QEMU-PASSED on 2026-10-21; NOT hardware-tested**.
Branch: `coral-phase11-userland-prep`.
Base: physically tested (owner-reported) Phase 10 Coral HFS+ RAM-root milestone.

## Demonstrated on Coral

- Physical XNU kernel entry and CPU0/timer/VM/IOKit/BSD initialization (Phase 08 video).
- RAM-only `md0` root and source-built static PID 1 with heartbeat (Phase 09 video).
- Owner reported `FLAME HFS: file read verified` and `SWEET init: still alive`
  during Phase 10 temporary boot, 2026-10-21.
- Phase 10 QEMU showed HFS mount, read, PID 1 and six heartbeats.
- This does **not** establish Apple `launchd`, `dyld`, CoreFoundation,
  SpringBoard or a working iOS graphical shell.

## Smallest next milestone

Verify a **second, separately code-signed static Mach-O process** can be
loaded from HFS+ RAM root and started using `fork` / `execve`, with
its own PID and test output, while PID 1 remains running.

Why: the existing static test binary being launched as PID 1 proves
kernel exec on boot but not independent on-disk process launch or
normal child process supervision. These are useful, smaller steps
before diagnosing Apple's dynamic loader.

Implemented Phase 11 hardware pass markers (NOT YET hardware-confirmed):

- `CORAL11: root HFS mounted`
- `CORAL11: child exec succeeded`
- `CORAL11: child exited status 0`
- `CORAL11: PID1 still alive`

Validate in QEMU first. Ship a **separate** temporary-boot image only
after emulator and host bounds/code-signature checks succeed.
The current `coral-hfs-ram10` image must remain untouched.

## Actual iOS userspace — prerequisites

1. A user-provided, lawfully obtained source of Apple iOS binaries,
   plus exact versions/architectures and the relevant shared cache.
   Do not bundle copyrighted firmware binaries into this public repo
   or public CI artifacts.
2. Inspect the actual launchd Mach-O load commands, dyld path,
   shared-cache architecture, filesystem symlinks and dependencies.
3. Verify that the small HFS-in-RAM approach can accommodate required
   components (1 GiB candidate kernel RAM; only partly characterized).
   Do not silently assume a complete iOS 16 root fits in RAM.
4. Resolve dynamic-linker, AMFI/code-signing, trust/entitlements,
   launchd startup, and missing IOKit/IORegistry services one stage at a time.
5. Only then assess framebuffer, IOSurface, BackBoard and SpringBoard
   paths. Borrow IOKit quiet/network fixes from
   `lgrachov/ios-sweet` only when actual logs justify them.

## Safety

- No UFS, no `userdata` formatting or flashing as part of Phase 11.
- Never treat a QEMU result as proof of real Pixel hardware safety.
- Do not issue `fastboot flash` or `fastboot erase`.
- Experimental XNU images do not guarantee an Android automatic reboot.
- RAM and framebuffer geometry are still partly inferred.

## Next implementation gate

**Completed:** all 3 GitHub Actions jobs passed in [run 39712670256](https://github.com/tutpyhoon/ios-coral/actions/runs/39712670256). macOS built separately ad-hoc signed ARM64 Mach-O programs; mounted/cleanly detached a 16 MiB HFS+ volume named CoralRAM; QEMU executed the second /bin/coral-child binary from that filesystem, reported exit status 0 to PID 1, and PID 1 continued printing heartbeats. A separate temporary-boot artifact `coral-phase11-child-exec-UNTESTED` was packaged. Phase 10 remains unchanged.

**Pending:** an actual Pixel 4 XL Phase 11 test; source-built probe only, not Apple launchd/SpringBoard. On-device XNU could still panic/hang; no automatic return to Android is guaranteed. The expected physical sequence is `hfs: mounted CoralRAM`, `CORAL11: PID1 HFS+ root active`, `CORAL11: fork succeeded, waiting for child`, `CORAL11: child exec succeeded`, `CORAL11: child exited status 0`, and `CORAL11: PID1 still alive`. The child success line comes from the secondary executable, not PID 1.
