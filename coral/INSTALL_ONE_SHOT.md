# One-command CORAL iOS 16 install/boot attempt (experimental)

**Target:** Google Pixel 4 XL (`coral`) ONLY.
**Not a confirmed boot of Apple's SpringBoard on Coral.**

This work integrates the completed [NWylynko/ios-flame](https://github.com/NWylynko/ios-flame)
XNU patch set (pinned commit `745c4341af86089efb0df851fa8a27fb8face624`)
with the owner's prior Pixel 4 XL device-tree framebuffer profile.
The complete XNU kernel **booted source-built PID 1 and child in QEMU**,
but **has not been physically tested on Coral**.
The upstream Pixel 4 (`flame`) has independently reported a real iOS
home-screen and Metal pipeline; these are **not** transferable success
claims for this Pixel 4 XL port.


> **October 22 kernel audit correction:** The compiled CORAL XNU kernel contains
> three unconditional UFS write fences. Even if an older boot image passes
> `ufsrw=1`, that does *not* enable storage writes. The latest UFS-root
> image intentionally requests `ufsrw=0 rootrw=0`. Apple launchd and
> SpringBoard have **not** been tested from such a read-only root. Run the
> separate `coral-full-flame-UFS-GPT-DIAG-UNTESTED` RAM-root probe **before**
> considering a full `userdata` replacement; it does not require wiping.

## What is built and available

- **Full Flame kernel + RAM test:** [run 39889361147](https://github.com/tutpyhoon/ios-coral/actions/runs/39889361147),
  artifact `coral-full-flame-RAM-UNTESTED`. `rd=md0`, `ufsrw=0`,
  `rootrw=0`, `sweetgpu=0`. Contains only source-built Phase 11 PID 1,
  not Apple's code. Used for **non-destructive temporary physical boot**.
- **Full Flame kernel + real iOS UFS root candidate:** *same run*, artifact
  `coral-full-flame-UFS-UNTESTED`. Boot args `rd=ufsroot0`,
  `ufsroot=userdata`, `ufsrw=0`, `rootrw=0`,
  `ignition_level=1`, `sweetgpu=0`. It includes **no iOS userland files**;
  those live on the private raw HFS+ image installed on userdata.
  **This version hard-blocks SCSI media writes in the compiled kernel** and has not booted
  or shown SpringBoard on Pixel 4 XL. Only consider it **after** checking
  the RAM candidate and your own recoverability.
- `coral/finalize_ios_root.py`: Mac-local iOS image export from the
  user's completed 24 GiB sparse HFS+ root. Mounts a **new copy** read/write,
  runs the pinned upstream `sweet-root-tweaks.py`, seeds the systembag,
  checks 44 shared-cache hard links, and validates/unwraps the
  Mac-created **Apple_HFSX GPT container**, producing pure raw HFS+ bytes
  at byte offset zero. **Original sparseimage remains unchanged**.
  Real macOS synthetic GPT extraction and CRC tests passed
  [run 39888505197](https://github.com/tutpyhoon/ios-coral/actions/runs/39888505197).
  The full owner's proprietary 24 GiB image itself has NOT been processed
  by GitHub or ChatGPT.
- `coral/deploy_ios_root.py`: default read-only inspect, with optional
  explicit destructive install. Verifies Android property `coral`,
  recovery ADB root, unmounted userdata, `/sys/class/block/xxx/uevent`
  `PARTNAME=userdata`, partition capacity, and raw HFS+ signature.
  Before installation it backs up `persist`, `modemst1`, `modemst2`,
  `fsg` and `fsc` privately. Writes **only** the verified
  `/dev/block/bootdevice/by-name/userdata` partition; reads first and
  last 4 KiB blocks back. **Erases LineageOS user data permanently.**
  It never flashes or erases bootloader/firmware/GPT/boot slots.
  Synthetic non-device guard tests passed
  [run 39888941793](https://github.com/tutpyhoon/ios-coral/actions/runs/39888941793).
- `coral/one_shot_coral.py`: combines local pinned upstream clone,
  artifact download, raw HFS+ finalization, calibration backups,
  guarded userdata install and **temporary** `fastboot boot` of full
  XNU UFS image. It cannot observe SpringBoard or guarantee iOS boot.

## CURRENT HARD BLOCK — do not run the destructive installer

The current full-Flame-Coral XNU build is **read-only at the SCSI driver
level** (three compiled UFS write fences). That prevents normal writable
launchd/`/private/var` operation. The Mac one-shot program now **refuses
these UFS images before userdata is touched**, even with
`--confirm ERASE_CORAL_USERDATA`.

First run the separate **temporary read-only GPT diagnostic** using
`coral/test_full_xnu_ufs.py` and [GitHub run
39891811910](https://github.com/tutpyhoon/ios-coral/actions/runs/39891811910).
It checks XNU's actual GPT `userdata` discovery and keeps Android's
filesystem intact. A subsequent new kernel build must safely enable
bounded writes to *that partition only* and be tested before the full
installer can proceed. The commands below describe the intended
eventual installation, not an currently usable finish operation.

## Minimum preparation — on the actual Mac

1. Back up all personal data. A `userdata` write cannot be undone
   without a restore.
2. Download the official **CORAL** factory image and a compatible
   **CORAL** recovery image. Do NOT use Flame's TWRP or factory image.
   Follow the [Pixel 4 XL TWRP guidance](https://twrp.me/google/googlepixel4xl.html)
   and independently confirm its compatibility with the currently
   installed bootloader.
3. Preserve `~/Coral-iOS-16-work/CoralIOSRoot.sparseimage` created
   earlier. It contains personally obtained Apple IPSW-derived binaries;
   **do not upload or commit this file**.
4. Have **at least 32 GiB available** on the Mac for conversion.
   Install and authenticate `gh`, and have `adb`, `fastboot`,
   `git` and the macOS `hdiutil` available.

One-time checkout:

```bash
git clone -b coral-flame-port --single-branch \
  https://github.com/tutpyhoon/ios-coral.git "$HOME/ios-coral-flame"
cd "$HOME/ios-coral-flame"
gh auth status
```

**Read-only preview (no phone or file writes):**

```bash
python3 coral/one_shot_coral.py --run-id 39889361147
```

### Irreversible installation attempt (owner-authorized only)

The physical RAM-only boot has **not** yet passed on Coral. Best practice
is to first download `coral-full-flame-RAM-UNTESTED` from the build run,
verify its SHA256, and temporary-boot that first; record the result.
The following option **does not wait for that gate** if the owner explicitly
chooses to proceed.

With the Coral phone unlocked, the *correct Coral recovery* image saved
locally and all data backed up, the single Mac command is:

```bash
python3 coral/one_shot_coral.py \
  --run-id 39889361147 \
  --source "$HOME/Coral-iOS-16-work/CoralIOSRoot.sparseimage" \
  --output "$HOME/Coral-iOS-16-complete" \
  --recovery "$HOME/Downloads/twrp-coral.img" \
  --execute \
  --confirm ERASE_CORAL_USERDATA
```

Replace the TWRP path with the actual compatible CORAL recovery `.img`.
The script automatically verifies the fastboot product is `coral` and
boots recovery temporarily. In rooted recovery, `/data` must be
UNMOUNTED; the script will stop otherwise. It then saves private
calibration images, installs the **RAW** iOS HFS+ partition to
`userdata`, verifies the first and last blocks, reboots to fastboot
and runs **`fastboot boot`** (never flash) for the experimental UFS
kernel. No Apple IPSW files are sent to GitHub.

**This is an attempted installation, not a guarantee.** It can stop on
Mac permissions or recovery compatibility, or the phone can bootloop,
panic, hang, fail to load dyld/launchd, fail to launch SpringBoard,
or display no image. The compiled upstream GPU/Metal stack has not been
tested on Coral; initial boot args deliberately disable GPU presentation.
Touchscreen and display hardware still differ from Pixel 4 (flame).

### Recovery

If the UFS-root kernel fails, hold power to return to the bootloader.
The safe recovery path is Google's full **CORAL factory image**, not Flame,
which restores stock Android and requires rebuilding userdata.
The private `persist`, `modemst1`, `modemst2`, `fsg`, `fsc` backups
must remain offline; never upload them to GitHub or anyone else.
The script does not replace those partitions.

## Open engineering work after installation attempt

The first physical **full** XNU start and UFS-mounted Apple launchd
are pending; the user must provide an on-device log/photo.
Only after that can genuine SpringBoard rendering be claimed.
Next blockers: Coral panel/DPU vs Flame 1080×2280 scanout, full RAM-map
validation, Apple root ownership and entitlements, root tweaks, then
Adreno 640 GPU firmware and SweetMetal2/Turnip userland built for iOS.
