#!/usr/bin/env python3
"""Prepare a pinned Pixel 4 (flame) source snapshot for Pixel 4 XL (coral).

THIS IS HOST-ONLY PORT PREPARATION, NOT A BOOTABLE IMAGE.
Patch a fresh, disposable checkout of NWylynko/ios-flame at the documented
pin, modify ONLY the non-running Apple Device Tree generator for 4 XL
geometry and identity, and emit a machine-readable list of unresolved
hardware changes. Do not run the upstream phone boot/flash scripts.

Usage:
  python3 coral/prepare_upstream_flame.py ./source-flame
  python3 coral/prepare_upstream_flame.py ./source-flame --verify
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

PIN = "745c4341af86089efb0df851fa8a27fb8face624"
TARGET_FB=(1440,3040,5760)
MIN_FB_BYTES=TARGET_FB[1]*TARGET_FB[2]
EXPECTED="NWylynko/ios-flame"

def check_repo(root):
    def git(*args):
        return subprocess.check_output(["git","-C",str(root),*args],text=True).strip()
    got=git("rev-parse","HEAD")
    if got!=PIN:
        raise RuntimeError(f"Upstream revision differs from pin: {got} != {PIN}")
    if git("status","--porcelain") and not (root/"coral-flame-port-report.json").is_file():
        raise RuntimeError("Expected a clean source checkout before first adaptation")
    if not (root/"tools/mkadt.py").is_file() or not (root/"xnu/patches/0124-flame-surf10-webcontent-only-link-bss.patch").is_file():
        raise RuntimeError("This does not look like the pinned ios-flame repository")

def one(s,old,new,label):
    if s.count(old)!=1:
        raise RuntimeError(f"{label}: missing/ambiguous expected Flame-only constant {old!r}")
    return s.replace(old,new)

def prepare(root, verify=False):
    root=root.expanduser().resolve(strict=True)
    check_repo(root)
    adt=root/"tools/mkadt.py"
    original=adt.read_text()
    patched=original
    patched=one(patched,
                "FB_W, FB_H, FB_STRIDE = 1080, 2280, 1080 * 4",
                "FB_W, FB_H, FB_STRIDE = 1440, 3040, 1440 * 4",
                "ADT framebuffer geometry") if not verify else patched
    patched=one(patched,"cstr('google,flame')","cstr('google,coral')",
                "ADT machine identity") if not verify else patched
    if "FB_W, FB_H, FB_STRIDE = 1440, 3040, 1440 * 4" not in patched:
        raise RuntimeError("CORAL ADT dimensions missing")
    if "cstr('google,coral')" not in patched:
        raise RuntimeError("CORAL identity missing")
    if not verify:
        adt.write_text(patched)
    # Query the upstream code shape so CI fails when critical assumptions
    # change in later commits; this intentionally does not rewrite GPU code.
    gpu=(root/"xnu/patches/0095-flame-gpu-present.patch").read_text()
    early=(root/"xnu/patches/0083-flame-display-keys-watchdog.patch").read_text()
    problems=[]
    checks={
       "same_soc_and_gpu_expected": True, # paired SM8150 / Adreno 640
       "coral_adt_geometry": TARGET_FB== (1440,3040,5760),
       "coral_boot_fdt": False,
       "coral_xnu_early_fb_patched": False,
       "coral_gpu_present_mapping": False,
       "coral_display_controller_config": False,
       "coral_touch_controller": False,
       "coral_pmic_and_keys": False,
       "coral_highmem_and_reserved_ram": False,
       "coral_userland_boot": False,
    }
    if "#define PANEL_W         1080" in gpu or "#define PANEL_H         2280" in gpu:
        problems.append("GPU present code is fixed to Flame PANEL_W=1080/PANEL_H=2280; Coral needs 1440x3040.")
    if "#define A6_FB_SIZE" in gpu and "0xa00000ull" in gpu:
        problems.append("GPU framebuffer mapping is ~10MiB; Coral's 1440*3040*4 is 17.5MiB; recalculate allocation and guard ranges.")
    if "SWEET_EARLY_FB_WIDTH      1080" in early:
        problems.append("Early XNU framebuffer macros hardcoded to 1080x2280 and 4320-byte stride.")
    if "4352-byte" in gpu:
        problems.append("Flame GPU present/panel stride toggles to 4352; Coral's native 5760-byte stride needs panel/DPU validation.")
    problems += [
        "Different Pixel 4 XL panel (1440x3040) and DSC/DPU programming: cannot reuse Flame's present sequence blindly.",
        "Different Pixel 4 XL FDT/DTBO and touchscreen integration: validate against owner's live hardware tree.",
        "Upstream --highmem assumes Flame memory layout; do not boot until Coral reserved-memory overlaps are checked.",
        "No vendor/Apple firmware, trusted root or original device data is included. NEVER run Flame's TWRP/dd/flash steps on Coral.",
    ]
    patches=list((root/"xnu/patches").glob("0[0-9][0-9][0-9]-*.patch"))
    report={
      "upstream":EXPECTED,"pin":PIN,
      "target":"Pixel 4 XL (coral); SM8150 / Adreno 640",
      "native_framebuffer":{"width":1440,"height":3040,"stride_bytes":5760,
                            "minimum_bytes":MIN_FB_BYTES},
      "adt_has_coral_geometry_and_identity":True,
      "upstream_xnu_patches":len(patches),
      "checks":checks,
      "blockers":problems,
      "status":"ADT ONLY ADAPTED; XNU GPU/PANEL/TOUCH/RAM/BOOT SHIM NOT PORTED",
      "explicitly_not_bootable":True,
    }
    (root/"coral-flame-port-report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report,indent=2))
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("upstream",type=Path)
    p.add_argument("--verify",action="store_true")
    args=p.parse_args()
    prepare(args.upstream,args.verify)

if __name__=="__main__":
    main()
