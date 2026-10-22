#!/usr/bin/env python3
"""Build an isolated Pixel 4 XL UFS read-only-media experiment.

Unlike register snapshot 06, this programs a UFS transfer queue and initiates
device-to-memory DMA. It can freeze hardware and is NOT cleared for physical
testing until FDT/host-memory/boot-image validations are reviewed.
Never flashes any partition and never sends a SCSI write command.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import build_probes as base


def replace_once(path, old, new):
    body = path.read_text()
    if body.count(old) != 1:
        raise RuntimeError(f"unexpected upstream source in {path}: {old!r}")
    path.write_text(body.replace(old, new))


def main():
    base.build()
    f = base.WORK / "flame"
    probe = f / "probe.c"
    header = Path(__file__).with_name("ufs_media12.h")
    source = header.read_text()
    for marker in ("opcode != 0x00 && opcode != 0x25 && opcode != 0x28",
                   "lba != 1 || bytes != UFS_BLOCK", "NO SCSI WRITE",
                   "CORAL12: GPT HEADER READ VERIFIED"):
        if marker not in source:
            raise RuntimeError("UFS media read safety boundary changed")
    (f / "coral_ufs_media12.h").write_text(source)
    replace_once(probe,
                 "void probe_main(uintptr_t fdt_address)",
                 "#ifdef PROBE_UFS_READ12\n#include \"coral_ufs_media12.h\"\n#endif\n"
                 "void probe_main(uintptr_t fdt_address)")
    replace_once(probe,
                 'line("PIXEL 4 XL / CORAL - UFS REG PROBE 06");',
                 'line("PIXEL 4 XL / CORAL - UFS MEDIA 12");')
    replace_once(probe,
                 'line("REGISTER SNAPSHOT COMPLETE");',
                 'line("REGISTER SNAPSHOT COMPLETE");\n'
                 '#ifdef PROBE_UFS_READ12\n'
                 '        coral_ufs_media_test();\n'
                 '#endif')
    replace_once(probe,
                 'line("NO REGISTER WRITES / NO DMA");',
                 '#ifdef PROBE_UFS_READ12\n'
                 '    line("QUEUE MMIO WRITES / READ DMA ONLY");\n'
                 '#else\n'
                 '    line("NO REGISTER WRITES / NO DMA");\n'
                 '#endif')
    replace_once(probe,
                 'line("NO STORAGE COMMANDS OR MEDIA ACCESS");',
                 '#ifdef PROBE_UFS_READ12\n'
                 '    line("READ-ONLY SCSI TUR/CAP/GPT COMMANDS");\n'
                 '#else\n'
                 '    line("NO STORAGE COMMANDS OR MEDIA ACCESS");\n'
                 '#endif')

    build = f / "build.sh"
    replace_once(build,
                 '01|02|03|04|06) ;;',
                 '01|02|03|04|06|12) ;;')
    replace_once(build,
                 'if [[ "$mode" == 06 ]]; then flags+=(-DPROBE_UFS); fi',
                 'if [[ "$mode" == 06 || "$mode" == 12 ]]; then flags+=(-DPROBE_UFS); fi\n'
                 'if [[ "$mode" == 12 ]]; then flags+=(-DPROBE_UFS_READ12); fi')
    replace_once(build,
                 "[01|02|03|04|05 PAYLOAD|06]",
                 "[01|02|03|04|05 PAYLOAD|06|12]")
    check = f / "check.py"
    replace_once(check,
                 'choices=["01", "02", "03", "04", "05", "06"]',
                 'choices=["01", "02", "03", "04", "05", "06", "12"]')

    base.command("bash", "flame/build.sh", "12", cwd=base.WORK)
    base.command(sys.executable, "flame/check.py", "12", cwd=base.WORK)
    src = f / "out/flame-probe-12.img"
    dst = base.OUT / "coral-ufs-media12-READ-ONLY-UNTESTED.img"
    shutil.copyfile(src, dst)
    result = {
        "device": "Google Pixel 4 XL / coral",
        "source_sha": base.FLAME_SHA,
        "boot_img": dst.name,
        "boot_sha256": hashlib.sha256(dst.read_bytes()).hexdigest(),
        "image_bytes": dst.stat().st_size,
        "controller_addr": "0x01d84000",
        "commands": ["TEST UNIT READY", "READ CAPACITY(10)", "READ(10) at LBA1 only"],
        "device_dma": True,
        "controller_queue_writes": True,
        "device_write_commands": False,
        "gpt_validation": "EFI PART only",
        "max_data_transfer": 4096,
        "physical_hardware_tested": False,
        "status": "EXPERIMENTAL NOT PHYSICAL-VALIDATED",
        "phone_partitions_flashing": False,
        "warning": "This temporary boot test writes controller queue registers and uses DMA; may freeze/reset or destabilize UFS. No device is contacted in GitHub CI.",
    }
    (base.OUT / "media12.json").write_text(json.dumps(result, indent=2) + "\n")
    (base.OUT / "SHA256SUMS-media12").write_text(
        f"{result['boot_sha256']}  {dst.name}\n")
    (base.OUT / "README-media12.txt").write_text(
        "CORAL 12 MEDIA READ — EXPERIMENTAL AND UNTESTED ON THE REAL PHONE\n"
        "READ-ONLY SCSI commands only. Programs UFS controller queue MMIO and issues READ DMA.\n"
        "It can hang the controller or cause an unexpected reset. Never flash.\n"
        "Target: Pixel 4 XL (coral) only. Source-built, not Apple's launchd or SpringBoard.\n"
        "Successful marker would be CORAL12: GPT HEADER READ VERIFIED.\n"
        "No filesystem mount, userdata write or persistent installation takes place.\n"
        "Do not interpret this as storage-driver readiness; the kernel lacks UFS.\n"
        "Only consider temporary fastboot boot with backup/recovery plan.\n"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
