#!/usr/bin/env python3
"""CORAL iOS HFS+ USERDATA deployer for a live, unlocked TWRP recovery.

Designed for Pixel 4 XL (coral) ONLY. Replaces Android USERDATA with the
already-exported, pure raw HFS+ iOS 16 root. This permanently erases user
data and Android boots will fail until the stock image is restored.

There is NO safe way to perform the final phone step in cloud CI.
The default is inspect-only. Destructive operation requires:
  --apply --confirm ERASE_CORAL_USERDATA --backup-dir PRIVATE_FOLDER

Defenses:
  - only physical Pixel 4 XL identity ('coral') via getprop;
  - adb root, recovery boot, exact /dev/block/bootdevice/by-name/userdata;
  - symlink resolves to ONE UFS physical partition, never 'super';
  - kernel sysfs PARTNAME must equal 'userdata';
  - image is raw HFS+ at offset 0, not Mac GPT or UDIF;
  - fits target partition with 4KiB sectors, /data is not mounted;
  - back up per-device persist, modemst1/2, fsg, fsc before ANY write;
  - written partition first and final 4KiB block read back and checked.

NEVER modify bootloader, modem, persist, fsg, fsc, GPT or super.
Does not itself reboot, flash a boot partition, or unlock the device.
Actual full iOS boot still depends on compatible CORAL XNU/GPU firmware and
userland fixes; a successful data write is NOT a home-screen guarantee.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from datetime import datetime,timezone

from hfs_partition_extract import hfs_header_at, GPTError

BYNAME="/dev/block/bootdevice/by-name"
BLOCK=4096
SENSITIVE=("persist","modemst1","modemst2","fsg","fsc")


class DeployError(RuntimeError):
    pass


def adb(*args, binary=False):
    proc=subprocess.run(["adb",*args],capture_output=True,check=False)
    if proc.returncode:
        raise DeployError(f"adb command failed: {args}: "+
                          proc.stderr.decode("utf-8","replace")[-400:])
    return proc.stdout if binary else proc.stdout.decode("utf-8","replace").strip()


def remote(command):
    return adb("shell","sh","-c",command)


def raw_info(image):
    p=Path(image).expanduser().resolve(strict=True)
    if not p.is_file() or p.suffix!=".img":
        raise DeployError("Supply an exported RAW .img from finalize_ios_root.py")
    size=p.stat().st_size
    if size<8*1024**3 or size>128*1024**3 or size%BLOCK:
        raise DeployError(f"Unexpected raw iOS root size {size}")
    with p.open("rb") as f:
        hfs=hfs_header_at(f,0,size)
        f.seek(512)
        if f.read(8)==b"EFI PART":
            raise DeployError("Refusing GPT container: need HFS+ starting at byte zero")
    return p,{"bytes":size, "hfs":hfs}


def device_info():
    """Remote checks do NOT access or alter any phone storage contents."""
    serials=[line for line in adb("devices").splitlines()[1:] if "\tdevice" in line]
    if len(serials)!=1:
        raise DeployError("Exactly one online ADB device is required")
    serial=serials[0].split("\t")[0]
    props={k:remote("getprop "+k) for k in (
        "ro.product.device","ro.product.vendor.device","ro.bootmode","ro.boot.mode")}
    if "coral" not in {props["ro.product.device"],props["ro.product.vendor.device"]}:
        raise DeployError("Device identity does not match Pixel 4 XL (coral)")
    # A rooted Android user build can report 'coral' and uid 0. Never
    # overwrite an actively running phone's userdata. An actual custom
    # recovery must report recovery as the boot mode.
    if not any(props[k] == "recovery" for k in ("ro.bootmode","ro.boot.mode")):
        raise DeployError("Device is NOT in recovery mode; never write userdata from Android")
    uid=remote("id -u").strip()
    if uid!="0":
        raise DeployError("Recovery ADB shell must run as root; do not try from normal Android")
    mounts=remote("cat /proc/mounts")
    for line in mounts.splitlines():
        parts=line.split()
        if len(parts)>=2 and parts[1] in ("/data","/sdcard","/mnt/userdata"):
            raise DeployError(f"Userdata is mounted at {parts[1]}: unmount in recovery first")
    byname=BYNAME+"/userdata"
    dest=remote("readlink -f "+shlex.quote(byname)).strip()
    if not re.fullmatch(r"/dev/block/sd[a-z][0-9]{1,3}",dest):
        raise DeployError(f"Unexpected userdata UFS block device target {dest!r}")
    devname=dest.rsplit("/",1)[1]
    event=remote("cat "+shlex.quote("/sys/class/block/"+devname+"/uevent"))
    if "PARTNAME=userdata" not in event.splitlines():
        raise DeployError("Device kernel does NOT identify this partition as userdata")
    size_txt=remote("blockdev --getsize64 "+shlex.quote(byname))
    try:
        size=int(size_txt)
    except ValueError as exc:
        raise DeployError(f"Could not read userdata size {size_txt!r}") from exc
    if size<8*1024**3 or size%BLOCK:
        raise DeployError("Unexpected userdata partition capacity")
    partition_readonly=remote("blockdev --getro "+shlex.quote(byname))
    if partition_readonly not in ("0","1"):
        raise DeployError("Cannot verify block device state")
    return {"serial":serial,"properties":props,"root_adb":True,
            "by_name":byname,"resolved":dest,"partname":"userdata",
            "partition_bytes":size,"block_device_readonly":partition_readonly,
            "userdata_unmounted":True}


def plan(image):
    p,details=raw_info(image)
    phone=device_info()
    if details["bytes"]>phone["partition_bytes"]:
        raise DeployError("Raw iOS filesystem is larger than the USERDATA partition")
    return {"status":"INSPECT ONLY — NO WRITES",
            "source_file":str(p),
            "source_raw_hfs":details,
            "device":phone,
            "userdata_will_be_erased_if_applied":True,
            "hardware_test_of_full_xnu":False,
            "springboard_boot_not_guaranteed":True}


def back_up_provisioning(folder,phone):
    root=folder.expanduser().absolute()
    if root.exists():
        if any(root.iterdir()):
            raise DeployError("Provisioning backup directory must be NEW and empty")
    else:
        root.mkdir(parents=True,mode=0o700)
    os.chmod(root,0o700)
    report={}
    for name in SENSITIVE:
        device=BYNAME+"/"+name
        # Use by-name, never assume per-device calibration partition numbers.
        found=remote("readlink -f "+shlex.quote(device))
        if not found.startswith("/dev/block/"):
            raise DeployError(f"Missing provisioning partition: {name}")
        partsize=int(remote("blockdev --getsize64 "+shlex.quote(device)))
        if not 4096<=partsize<=64*1024*1024:
            raise DeployError(f"Provisioning partition {name} has unexpected size")
        out=root/(name+".img")
        command=["adb","exec-out","sh","-c",
                 "dd if="+shlex.quote(device)+" bs=1048576 2>/dev/null"]
        with out.open("xb") as fd:
            p=subprocess.run(command,stdout=fd,stderr=subprocess.PIPE,check=False)
        if p.returncode or out.stat().st_size!=partsize:
            raise DeployError(f"Backup of {name} failed; STOP BEFORE ANY WRITES")
        with out.open("rb") as backup_fd:
            digest=hashlib.file_digest(backup_fd,"sha256").hexdigest()
        report[name]={"file":out.name,"bytes":partsize,"sha256":digest}
    (root/"manifest.json").write_text(json.dumps({
        "device":"coral","private_per_device_calibration":True,
        "note":"DO NOT UPLOAD THESE IMEI/CALIBRATION BACKUPS TO PUBLIC GITHUB",
        "files":report
    },indent=2)+"\n")
    print("Backed up persist/modemst1/modemst2/fsg/fsc to",root,flush=True)
    return report


def read_device_block(remote_device,sector):
    cmd=["adb","exec-out","sh","-c",
         "dd if="+shlex.quote(remote_device)+
         " bs=4096 skip="+str(sector)+" count=1 2>/dev/null"]
    r=subprocess.run(cmd,capture_output=True,check=False)
    if r.returncode or len(r.stdout)!=BLOCK:
        raise DeployError(f"Cannot read-back block {sector}")
    return r.stdout


def install(image,backup_dir,confirmation):
    if confirmation!="ERASE_CORAL_USERDATA":
        raise DeployError("Destructive installation requires the exact confirmation token")
    info=plan(image)
    if info["device"]["block_device_readonly"]!="0":
        raise DeployError("Recovery identifies userdata block device as read-only")
    source=Path(info["source_file"])
    size=info["source_raw_hfs"]["bytes"]
    phone=info["device"]
    # Capture both sensitive provisioning and host-first/last comparison
    # before allowing the one and only media write.
    back_up_provisioning(backup_dir,phone)
    with source.open("rb") as f:
        first=f.read(BLOCK)
        f.seek(size-BLOCK)
        last=f.read(BLOCK)
    print("WARNING: USERDATA WILL BE OVERWRITTEN; calibration partitions preserved.")
    print(f"Phone: {phone['serial']}  target: {phone['resolved']}  bytes: {size}")
    # Single write: exact /dev/block/by-name/userdata. No shell variable from
    # device output is interpolated into the command.
    command=["adb","exec-in","sh","-c",
             "dd of="+shlex.quote(phone["by_name"])+
             " bs=4194304 conv=fsync"]
    with source.open("rb") as fd:
        p=subprocess.run(command,stdin=fd,capture_output=True,check=False)
    if p.returncode:
        raise DeployError("ROOT WRITE FAILED: PHONE USERDATA IS NOW PARTIAL; recovery required")
    if read_device_block(phone["by_name"],0)!=first:
        raise DeployError("First HFS block READBACK MISMATCH: stop, do not boot iOS")
    if read_device_block(phone["by_name"],size//BLOCK-1)!=last:
        raise DeployError("Final HFS block READBACK MISMATCH: stop, do not boot iOS")
    # A first/last block check can miss corrupted transfers in the middle.
    # Check three additional deterministic blocks without reading private
    # user data to the CI/server. These are still samples, not a full hash.
    for block_index in (size//(BLOCK*4), size//(BLOCK*2),
                        (size//BLOCK)*3//4):
        with source.open("rb") as source_fd:
            source_fd.seek(block_index*BLOCK)
            expected=source_fd.read(BLOCK)
        if read_device_block(phone["by_name"],block_index)!=expected:
            raise DeployError(f"Middle block {block_index} READBACK MISMATCH; do not boot")
    print(json.dumps({
        "status":"USERDATA REPLACED WITH RAW HFS+; FIVE READBACK SAMPLES MATCH (NOT FULL VERIFICATION)",
        "device":"coral","wrote_bytes":size,
        "backup_dir":str(backup_dir),
        "next":"Only a validated CORAL-specific full-XNU UFS-root boot image can use this",
        "springboard_appeared":False
    },indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("root_img",type=Path)
    p.add_argument("--apply",action="store_true")
    p.add_argument("--confirm",default="")
    p.add_argument("--backup-dir",type=Path)
    args=p.parse_args()
    try:
        if args.apply:
            if args.backup_dir is None:
                p.error("--apply requires --backup-dir")
            install(args.root_img,args.backup_dir,args.confirm)
        else:
            print(json.dumps(plan(args.root_img),indent=2))
    except (DeployError,ValueError,OSError,GPTError) as exc:
        p.error(str(exc))

if __name__=="__main__":
    main()
