#!/usr/bin/env python3
"""Offline source adaptation of the pinned ios-flame shim to Pixel 4 XL.

DOES NOT generate an Android boot image or touch a phone.
The first CORAL shim must not write the upstream Flame scratch/rescue area
inside userdata or reprogram Flame-specific DPU autorefresh registers.
Disables shim UFS logging completely and uses Coral's measured FB geometry.
An eventual boot image still requires the *real Coral boot DTB* and a
separately validated payload; no Flame factory assets may be substituted.
"""
from pathlib import Path
import argparse


def change(path, needle, replacement):
    src=path.read_text()
    n=src.count(needle)
    if n != 1:
        raise RuntimeError(f"STOP: {path.name}: expected 1 occurrence of {needle!r}; found {n}")
    path.write_text(src.replace(needle,replacement))


def adapt(root):
    root=root.resolve(strict=True)
    if not (root/"shim/shim.c").is_file() or not (root/"shim/console.h").is_file():
        raise RuntimeError("Expected a pinned Flame upstream source checkout")

    hdr=root/"shim/console.h"
    change(hdr, "#define FB_W\t\t1080", "#define FB_W\t\t1440")
    change(hdr, "#define FB_H\t\t2280", "#define FB_H\t\t3040")

    main=root/"shim/shim.c"
    change(main,
           "\tufs_ok = !ufs_init();\n\tif (ufs_ok)\n\t\tramlog_rescue();",
           "\t/* CORAL SAFE: do not take over the UFS controller or write\n"
           "\t * Flame's scratch/rescue LBA ranges (different partitions).\n"
           "\t * XNU must initialize its own controller later.\n"
           "\t */\n"
           "\tufs_ok = 0;\n"
           "\tlog_printf(\"CORAL: UFS scratch logging/rescue disabled\\n\");")
    change(main,
           '\tsde_autorefresh(1);\n\tsde_sample("autorefresh", 16, 20);',
           '\t/* CORAL SAFE: no writes to the Flame DPU autorefresh registers. */\n'
           '\tsave_log("coral display: no dpu writes");')
    change(main,'con_str("FLAME", "shim probe v1");',
           'con_str("CORAL", "read-only shim probe");')
    # The runtime path must keep the UFS logging gate permanently closed.
    content=main.read_text()
    if content.count("ufs_ok = 0;")!=1 or "ufs_ok = !ufs_init();" in content:
        raise RuntimeError("STOP: shim scratch UFS may be active")
    if 'log_printf("CORAL: UFS scratch logging/rescue disabled' not in content:
        raise RuntimeError("STOP: missing disabled-logging message")
    if "struct loader_fb lfb = { fb, stride, FB_W, FB_H, save_before_jump };" not in content:
        raise RuntimeError("STOP: loader geometry contract changed")
    if "#define FB_W\t\t1440" not in hdr.read_text() or "#define FB_H\t\t3040" not in hdr.read_text():
        raise RuntimeError("STOP: missing Coral framebuffer geometry")
    print("PASS: Coral source shim geometry adapted, no UFS logging/rescue, no unverified DPU autorefresh in normal path")
    print("This does not validate the Qualcomm display pipe or construct a device boot image.")


if __name__=="__main__":
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("checkout",type=Path)
    adapt(ap.parse_args().checkout)
