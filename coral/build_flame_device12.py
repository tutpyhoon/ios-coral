#!/usr/bin/env python3
"""Assemble a NON-FLASH temporary Pixel 4 XL full-Flame XNU boot.img.

Inputs are exact artifacts from PASSED runs and a previously booted CORAL
Android v2 boot.img. The input boot image is read only: its DTB is reused.
The kernel is the full Flame-0124 + Coral framebuffer and QEMU-only SPMI
guard, but on physical Coral it runs WITHOUT coralqemu=1.

No internal UFS or partition write: rd=md0, rootrw=0, ufsrw=0, sweetgpu=0.
This is the 16 MiB source-built test root, NOT Apple's real SpringBoard.
This first-boot image may still hang or panic; flash it to NO partition.
All inputs must be supplied. This script never uses adb or fastboot.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

CORAL_REF_BOOT_SHA256="3eba87e4b4a946f8a716bda809c7540759a53943130ae52069933a41b57cacd4"
CORAL_REF_DTB_SHA256="f582348d19807e8f4681e6c226c9947ef64a380ef1c85c487458f7bf085b89da"
PIN="745c4341af86089efb0df851fa8a27fb8face624"
PHYS_BASE=0x100000000
PHYS_SIZE=0x40000000   # Exact 1 GiB candidate proven in prior on-device Phase 11
FB=(0x9c400000,1440,3040,5760)
CMDLINE=(
    "debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress "
    "rd=md0 rootrw=0 ufsrw=0 sweetgpu=0 wdt=-1"
)
UFS_CMDLINE=(
    "debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress "
    "rd=ufsroot0 ufsroot=userdata ufsrw=0 rootrw=0 sweetgpu=0 "
    "unentitled_ios_sim_launch=1 ignition_level=1 launchd_unsecure_cache=1 "
    "wdt_test=no_user_checkin wdt=-1"
)
UFS_DIAG_CMDLINE=(
    "debug=0xc serial=3 cpus=1 keepsyms=1 -enable_kprintf_spam -noprogress "
    "rd=md0 rootrw=0 ufsrw=0 coralufsdiag=1 sweetgpu=0 wdt=-1"
)
SOURCES="start.S shim.c console.c log.c util.c mmu.c fdt.c loader.c ufs.c spmi.c sde.c showlog.c diag.c disptest.c gpuprobe.c gpufw.S smmuprobe.c ramlog.c".split()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def run(args, *, cwd=None):
    argv=list(map(str,args))
    print("+", " ".join(argv),flush=True)
    subprocess.run(argv,cwd=cwd,check=True)


def checked_ref_boot(path, audit):
    raw=path.read_bytes()
    if sha(raw)!=CORAL_REF_BOOT_SHA256:
        raise ValueError("Reference boot image is not the previously photographed Phase11 image; obtain the exact artifact")
    report,dtb=audit.inspect(raw)
    if report["dtb_sha256"]!=CORAL_REF_DTB_SHA256:
        raise ValueError("Reference boot DTB fingerprint changed")
    if report["header_version"]!=2 or report["page_size"]!=4096:
        raise ValueError("Boot header format does not match proven Coral variant")
    # The prior boot passed on physical CORAL but that is not equivalent to
    # a full board-revision compatibility or RAM-map proof.
    return dtb,report


def patch_adt(path, tools_dir):
    sys.path.insert(0,str(tools_dir))
    import adt
    buf=path.read_bytes()
    tree,off=adt.parse(buf)
    if off!=len(buf):
        raise ValueError("Corrupt ADT trailing bytes")
    chosen=next(c for c in tree.children if c.name=="chosen")
    properties=dict((n,v) for n,_,v in chosen.props)
    if int.from_bytes(properties["dram-base"],"little")!=PHYS_BASE:
        raise ValueError("Full Flame ADT not in highmem mode")
    old=int.from_bytes(properties["dram-size"],"little")
    if old<PHYS_SIZE:
        raise ValueError("Highmem ADT memory smaller than 1GiB")
    chosen.props=[(n,flags,struct.pack("<Q",PHYS_SIZE) if n=="dram-size" else val)
                  for n,flags,val in chosen.props]
    display=next((c for c in tree.children if c.name=="arm-io"),None)
    if not display or b"google,coral" not in buf:
        raise ValueError("Missing Coral identity or arm-io in ADT")
    out=adt.serialize(tree)
    assert b"google,coral" in out
    path.write_bytes(out)
    return {"dram_base":hex(PHYS_BASE),"dram_size":hex(PHYS_SIZE),
            "fb_phys":hex(FB[0]),"fb_width":FB[1],"fb_height":FB[2],
            "fb_stride":FB[3]}


def build(source,tools_dir,kernel,ramroot,reference,out,root_mode="ram"):
    if root_mode not in ("ram","ufs","ufsdiag"):
        raise ValueError("Only RAM test or physical UFS root modes are available")
    source=source.expanduser().resolve(strict=True)
    tools_dir=tools_dir.expanduser().resolve(strict=True)
    out=out.expanduser().absolute()
    if out.exists():
        raise ValueError(f"Refusing overwrite: {out}")
    if not out.parent.is_dir():
        raise ValueError("Output parent must exist")
    if out.suffix!=".img":
        raise ValueError("Output must be a new .img file")
    if sha(reference.read_bytes())!=CORAL_REF_BOOT_SHA256:
        raise ValueError("Wrong reference boot.img")
    from audit_bootimg_v2 import inspect
    dtb,original=checked_ref_boot(reference,sys.modules["audit_bootimg_v2"])
    if kernel.stat().st_size<100000 or kernel.read_bytes()[:4]!=b"\xcf\xfa\xed\xfe":
        raise ValueError("Expected large unwrapped XNU ARM64 Mach-O")
    if ramroot.stat().st_size!=16*1024*1024:
        raise ValueError("Expected exactly the original 16MiB Phase11 RAM HFS filesystem")
    if b"CORAL11: child exec succeeded" not in ramroot.read_bytes():
        raise ValueError("Incorrect RAM filesystem; not original test userspace")
    subprocess.run(["git","-C",str(source),"diff","--quiet"],check=False)
    # The caller stages the source adaptations; protect against accidental
    # later updates or use of the Flame phone's unpatched shim.
    import re
    hdr=(source/"shim/console.h").read_text()
    main=(source/"shim/shim.c").read_text()
    if not re.search(r"#define FB_W\s+1440\b",hdr) or not re.search(r"#define FB_H\s+3040\b",hdr):
        raise ValueError("Coral shim display dimensions not adapted")
    if "ufs_ok = !ufs_init();" in main or "ramlog_rescue();" in main:
        raise ValueError("Persistent Flame scratch logging may be enabled")
    if "UFS scratch logging/rescue disabled" not in main:
        raise ValueError("No explicit Coral UFS safety fence")
    build_dir=out.parent/(out.stem+"-engineering")
    if build_dir.exists():
        raise ValueError("Refusing overwrite of previous engineering outputs")
    build_dir.mkdir()
    dtb_path=build_dir/"reference-coral.dtb"
    dtb_path.write_bytes(dtb)
    adt_path=build_dir/"coral-physical.adt"
    payload_path=build_dir/"coral-full-xnu-hfs.payload"
    run([sys.executable,source/"tools/mkadt.py",adt_path,"--highmem"])
    ram=patch_adt(adt_path,source/"tools")
    payload_args=[sys.executable,source/"tools/mkpayload.py",kernel,
                  adt_path,payload_path,"--cmdline",
                  UFS_CMDLINE if root_mode=="ufs" else
                  (UFS_DIAG_CMDLINE if root_mode=="ufsdiag" else CMDLINE)]
    if root_mode in ("ram","ufsdiag"):
        payload_args.extend(["--ramdisk",ramroot])
    run(payload_args)
    payload=payload_path.read_bytes()
    assert payload[:8]==b"SWEETXNU"
    if b"coralqemu=1" in payload:
        raise ValueError("Physical package must not contain the emulator-only boot argument")
    if root_mode in ("ram","ufsdiag"):
        if any(x in payload for x in (b"rd=ufsroot0",b"ufsrw=1",b"rootrw=1")):
            raise ValueError("Unsafe UFS activation in RAM-root test")
        required=(b"rd=md0",b"ufsrw=0",b"rootrw=0",b"sweetgpu=0")
        if root_mode=="ufsdiag":
            required += (b"coralufsdiag=1",)
        elif b"coralufsdiag=1" in payload:
            raise ValueError("Unexpected XNU UFS diagnostic in base RAM test")
    else:
        # XNU Mach-O contains the literal RAMDisk name as code, not an ADT RAM root.
        if b"rd=md0" in payload:
            raise ValueError("UFS-root build unexpectedly contains a RAM root")
        required=(b"rd=ufsroot0",b"ufsroot=userdata",b"ufsrw=0",
                  b"rootrw=0",b"ignition_level=1",b"sweetgpu=0")
    if not all(x in payload for x in required):
        raise ValueError("Missing boot arguments for selected root mode")
    if struct.unpack_from("<Q",payload,0x38)[0]!=PHYS_BASE:
        raise ValueError("Payload physical target incorrect")
    # Compile fresh safe Coral shim source. This is a host build only.
    objs=[]
    for filename in SOURCES:
        obj=build_dir/(filename.rsplit(".",1)[0]+".o")
        run(["clang","--target=aarch64-none-elf","-O2","-ffreestanding","-nostdlib",
             "-fno-builtin","-fno-pic","-fno-pie","-mgeneral-regs-only",
             "-mstrict-align","-fno-stack-protector",
             "-fno-asynchronous-unwind-tables","-Wall","-Wextra",
             "-I",source/"shim","-c",source/"shim"/filename,"-o",obj])
        objs.append(obj)
    elf=build_dir/"coral-shim.elf"
    run(["ld.lld","-static","-nostdlib","-T",source/"shim/shim.ld","--build-id=none",
         "-N",*objs,"-o",elf])
    kernel_image=build_dir/"Image"
    run(["llvm-objcopy","-O","binary",elf,kernel_image])
    nm=subprocess.check_output(["llvm-nm",str(elf)],text=True)
    matches=re.findall(r"^([0-9a-fA-F]+)\s+\w\s+_end$",nm,re.M)
    if len(matches)!=1:
        raise ValueError("Could not determine exact shim BSS+stack image size")
    end=int(matches[0],16)
    with kernel_image.open("r+b") as f:
        f.truncate(end)
    compressed=build_dir/"Image.lz4"
    run(["lz4","-q","-9","-B7","-f",kernel_image,compressed])
    # Use pinned AOSP's own mkbootimg and AVB scripts, supplied in the
    # local tools directory. No external file is downloaded or flashed here.
    mkbootimg=tools_dir/"downloads/mkbootimg/mkbootimg.py"
    avbtool=tools_dir/"downloads/avb/avbtool.py"
    if not mkbootimg.is_file() or not avbtool.is_file():
        raise ValueError("Missing pinned AOSP mkbootimg/avbtool under tools/downloads")
    run([sys.executable,mkbootimg,
         "--header_version","2","--kernel",compressed,"--ramdisk",payload_path,
         "--dtb",dtb_path,"--base","0","--kernel_offset","0x8000",
         "--ramdisk_offset","0x1000000","--tags_offset","0x100",
         "--dtb_offset","0x1f00000","--pagesize","4096",
         "--os_version","13.0.0","--os_patch_level","2022-10",
         "--cmdline","console=null","-o",out])
    run([sys.executable,avbtool,"add_hash_footer","--image",out,
         "--partition_size","67108864","--partition_name","boot"])
    image=out.read_bytes()
    if len(image)!=67108864:
        raise ValueError("Not a 64MiB AVB footer-bearing experimental boot.img")
    report,dtb2=inspect(image)
    if sha(dtb2)!=CORAL_REF_DTB_SHA256:
        raise ValueError("Packaged boot DTB does not match owner hardware reference")
    # The header's ramdisk section must carry the exact payload just built.
    part=report["sections"]["ramdisk"]
    if image[part["offset"]:part["offset"]+part["size"]]!=payload:
        raise ValueError("Packed boot ramdisk does not match the audited XNU payload")
    manifest={
        "status":"NEW PHYSICAL TEMPORARY BOOT CANDIDATE — NOT TESTED ON CORAL",
        "model":"Pixel 4 XL (coral)",
        "full_flame_source_pin":PIN,
        "mac_or_ci_only":True,
        "only_fastboot_boot_supported":True,
        "never_flash_or_erase":True,
        "ios_springboard":False,
        "apple_launchd":False,
        "root":("source-built Phase11 16MiB HFS+ RAM only" if root_mode=="ram" else
                "Phase11 RAM HFS+ with XNU-only UFS GPT diagnostic" if root_mode=="ufsdiag" else
                "UFS partition named userdata: read-only private iOS HFS+ root"),
        "root_mode":root_mode,
        "ufs_media_write_commands_enabled":False,
        "kernel_has_three_ufs_write_fences":True,
        "coralufsdiag":root_mode=="ufsdiag",
        "tested_with_apple_launchd":False,
        "userdata_must_be_installed_first":root_mode=="ufs",
        "ram":ram,
        "kernel_sha256":sha(kernel.read_bytes()),
        "hfs_sha256":sha(ramroot.read_bytes()) if root_mode in ("ram","ufsdiag") else None,
        "boot_sha256":sha(image),
        "boot_img":out.name,
        "dtb_sha256":sha(dtb2),
        "reference_boot_sha256":sha(reference.read_bytes()),
        "risk":"Full experimental kernel can panic, freeze or reset; high RAM carveout and DPU not independently cleared",
        "no_phone_access_in_build":True,
    }
    (build_dir/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (build_dir/"SHA256SUMS").write_text(f"{sha(image)}  {out.name}\n")
    print(json.dumps(manifest,indent=2))
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("source","tools","kernel","ramroot","reference_boot","output"):
        p.add_argument("--"+name.replace("_","-"),type=Path,required=True)
    p.add_argument("--root-mode",choices=("ram","ufs","ufsdiag"),default="ram")
    args=p.parse_args()
    build(args.source,args.tools,args.kernel,args.ramroot,
          args.reference_boot,args.output,args.root_mode)

if __name__=="__main__":
    main()
