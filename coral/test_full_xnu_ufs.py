#!/usr/bin/env python3
"""One-command temporary CORAL full-XNU UFS-GPT diagnostic (NO FLASH/ERASE).

Download CI artifact from matching run, validate manifest and checksum,
identify actual Pixel 4 XL in fastboot, and TEMPORARILY boot the diagnostic.
Only reads the internal GPT through XNU's upstream UFS driver. The
controller registers/queue ARE modified and device-to-memory DMA is used;
a hang/reboot is possible. No storage write CDB or partition install.

Usage:
  python3 coral/test_full_xnu_ufs.py --run-id BUILD_RUN_ID
  python3 coral/test_full_xnu_ufs.py --run-id BUILD_RUN_ID --execute

Default is a plan. Device actions require --execute --confirm BOOT_CORAL_UFS_DIAG.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

REPO="tutpyhoon/ios-coral"
ARTIFACT="coral-full-flame-UFS-GPT-DIAG-UNTESTED"
IMAGE_NAME="coral-full-flame-UFS-GPT-DIAG-UNTESTED.img"
DEVICE="coral"
CONFIRM="BOOT_CORAL_UFS_DIAG"

def digest(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f,"sha256").hexdigest()

def verify(folder):
    folder=Path(folder)
    paths={n:folder/n for n in (IMAGE_NAME,"manifest.json","SHA256SUMS")}
    if not all(p.is_file() for p in paths.values()):
        raise ValueError("Missing diagnostic image, checksum or manifest")
    manifest=json.loads(paths["manifest.json"].read_text())
    assert manifest.get("root_mode")=="ufsdiag"
    assert manifest.get("coralufsdiag") is True
    assert manifest.get("kernel_has_three_ufs_write_fences") is True
    assert manifest.get("ufs_media_write_commands_enabled") is False
    assert manifest.get("hfs_sha256")
    assert manifest.get("model")=="Pixel 4 XL (coral)"
    assert manifest.get("dtb_sha256")=="f582348d19807e8f4681e6c226c9947ef64a380ef1c85c487458f7bf085b89da"
    image=paths[IMAGE_NAME]
    if image.stat().st_size!=67108864:
        raise ValueError("Incorrect experimental Android v2 boot image size")
    actual=digest(image)
    expect=manifest.get("boot_sha256")
    checksum=paths["SHA256SUMS"].read_text().split()
    if len(checksum)!=2 or checksum[0]!=actual or checksum[1]!=IMAGE_NAME or expect!=actual:
        raise ValueError("SHA256SUMS / manifest mismatch: do NOT boot")
    return manifest

def plan(run_id):
    if run_id<=0:
        raise ValueError("Run ID must be positive")
    return {
        "model":"Pixel 4 XL coral ONLY",
        "artifact":ARTIFACT,
        "run_id":run_id,
        "root":"source-built HFS+ RAM disk (NOT iOS userland)",
        "checks":"full XNU controller init, SCSI readiness and GPT partition name",
        "no_userdata_install":True,
        "no_scsi_media_writes":True,
        "changes_ufs_controller_registers":True,
        "uses_ufs_dma":True,
        "physical_status":"NOT YET HARDWARE TESTED",
        "danger":"May hang/reset phone; keep verified Android recovery.",
        "required_confirmation":CONFIRM
    }

def check_fastboot_coral():
    p=subprocess.run(["fastboot","getvar","product"],capture_output=True,text=True)
    result=p.stdout+"\n"+p.stderr
    if p.returncode or not any(
        line.strip().lower().endswith("product: coral") for line in result.splitlines()
    ):
        raise ValueError("STOP: fastboot does not report product: coral")

def execute(run_id,output,confirm):
    if confirm!=CONFIRM:
        raise ValueError("STOP: --execute requires --confirm BOOT_CORAL_UFS_DIAG")
    for tool in ("gh","adb","fastboot"):
        if shutil.which(tool) is None:
            raise ValueError(f"Missing prerequisite: {tool}")
    out=Path(output).expanduser().absolute()
    if out.exists():
        if not out.is_dir() or any(out.iterdir()):
            raise ValueError("Refusing to overwrite the output directory")
    else:
        out.mkdir(parents=True)
    subprocess.run(["gh","run","download",str(run_id),"-R",REPO,
                    "-n",ARTIFACT,"-D",str(out)],check=True)
    manifest=verify(out)
    print("PASS: diagnostic image SHA256 and CORAL hardware identity manifest")
    p=subprocess.run(["adb","devices"],capture_output=True,text=True)
    if p.returncode:
        raise ValueError("Cannot query ADB; connect the Pixel 4 XL")
    # If device is already in fastboot there need not be an ADB device;
    # do not silently send 'adb reboot' to a different device.
    if not any("\tdevice" in line for line in p.stdout.splitlines()[1:]):
        print("ADB device unavailable; expecting CORAL already in fastboot")
    else:
        connected=[line for line in p.stdout.splitlines()[1:] if "\tdevice" in line]
        if len(connected)!=1:
            raise ValueError("Exactly one connected ADB device is required")
        dev=subprocess.run(["adb","shell","getprop","ro.product.device"],
                           capture_output=True,text=True,check=True).stdout.strip()
        if dev!="coral":
            raise ValueError(f"ADB target is {dev!r}, not coral")
        subprocess.run(["adb","reboot","bootloader"],check=True)
    check_fastboot_coral()
    # The ONLY device-changing operation. It temporarily boots a signed-
    # format Android boot.img; it is never written to a phone partition.
    subprocess.run(["fastboot","boot",str(out/IMAGE_NAME)],check=True)
    print("DIAGNOSTIC BOOT SENT. Photograph the screen with CORAL UFS DIAG")
    print("Success is 'CORAL UFS DIAG: GPT userdata FOUND, rc=0'")
    print("Failure may be a hang, panic or missing framebuffer; do not flash.")

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id",required=True,type=int)
    p.add_argument("--output",type=Path,default=Path.home()/"Coral-XNU-GPT-Test")
    p.add_argument("--execute",action="store_true")
    p.add_argument("--confirm",default="")
    args=p.parse_args()
    try:
        if args.execute: execute(args.run_id,args.output,args.confirm)
        else: print(json.dumps(plan(args.run_id),indent=2))
    except (OSError,ValueError,AssertionError,subprocess.CalledProcessError) as e:
        p.error(str(e))

if __name__=="__main__":
    main()
