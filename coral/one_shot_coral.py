#!/usr/bin/env python3
"""One-command *LOCAL MAC* end-to-end Coral iOS root installer and boot attempt.

Runs only when explicitly --execute --confirm ERASE_CORAL_USERDATA.
Requires: own completed CoralIOSRoot.sparseimage, macOS, GitHub CLI
authenticated, working ADB/fastboot and a compatible ROOTED Coral recovery.
Downloads the pinned full-Flame UFS-boot artifact, finalizes real iOS root
and preserves per-device modem calibration before replacing USERDATA.

One command CANNOT guarantee real SpringBoard will boot. Full Flame XNU,
GPU driver, touch and DPU are NOT yet hardware-proven on Pixel 4 XL.
A failure after writing userdata may require restoring stock Android;
never use the same device as your only daily-use phone.

By default this tool only prints the plan; no operation is performed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

UPSTREAM_SHA="745c4341af86089efb0df851fa8a27fb8face624"
REPO="tutpyhoon/ios-coral"
ARTIFACT="coral-full-flame-UFS-UNTESTED"

def command(cmd,*,cwd=None):
    args=list(map(str,cmd))
    print("+", " ".join(args),flush=True)
    subprocess.run(args,check=True,cwd=cwd)

def get_output(cmd):
    return subprocess.run(list(map(str,cmd)),check=True,
                          capture_output=True,text=True).stdout.strip()

def ensure_mac():
    if sys.platform!="darwin":
        raise RuntimeError("Run locally on the user's Mac, not a server")
    for name in ("git","gh","adb","fastboot","hdiutil","python3"):
        if shutil.which(name) is None:
            raise RuntimeError(f"Missing {name} — install and configure it before continuing")

def fresh_folder(path):
    path=path.expanduser().absolute()
    if path.exists():
        if not path.is_dir() or any(path.iterdir()):
            raise RuntimeError(f"Refusing to overwrite existing output: {path}")
    return path

def checked_boot_img(folder):
    manifest_path=folder/"manifest.json"
    sha_path=folder/"SHA256SUMS"
    img=folder/"coral-full-flame-UFS-UNTESTED.img"
    if not all(p.is_file() for p in (manifest_path,sha_path,img)):
        raise RuntimeError("Missing UFS-boot artifact files")
    manifest=json.loads(manifest_path.read_text())
    if manifest.get("root_mode")!="ufs" or not manifest.get("userdata_must_be_installed_first"):
        raise RuntimeError("Downloaded artifact is not the intended full-iOS UFS root build")
    if manifest.get("full_flame_source_pin")!=UPSTREAM_SHA or manifest.get("model")!="Pixel 4 XL (coral)":
        raise RuntimeError("Downloaded artifact has an unexpected source or phone")
    expected=manifest.get("boot_sha256")
    if hashlib.file_digest(img.open("rb"),"sha256").hexdigest()!=expected:
        raise RuntimeError("Full Flame UFS boot image checksum mismatch")
    digest=sha_path.read_text().strip().split()[0]
    if digest!=expected:
        raise RuntimeError("Published SHA256SUMS does not match artifact manifest")
    return img

def fastboot_coral():
    result=subprocess.run(["fastboot","getvar","product"],
                          capture_output=True,text=True,check=False)
    both=result.stdout+"\n"+result.stderr
    if result.returncode or not any("product: coral" in line.lower() for line in both.splitlines()):
        raise RuntimeError("fastboot is not connected to a Pixel 4 XL (coral)")

def source_checkout(upstream):
    if upstream.exists():
        raise RuntimeError("Upstream checkout already exists in the output folder")
    command(["git","init","-q",upstream])
    command(["git","-C",upstream,"fetch","-q","--depth","1",
             "https://github.com/NWylynko/ios-flame.git",UPSTREAM_SHA])
    command(["git","-C",upstream,"checkout","-q","--detach","FETCH_HEAD"])
    sha=get_output(["git","-C",upstream,"rev-parse","HEAD"])
    if sha!=UPSTREAM_SHA:
        raise RuntimeError("Source commit changed during download")
    return upstream/"tools/sweet-root-tweaks.py"

def execute(source,output,run_id,recovery,confirm):
    if confirm!="ERASE_CORAL_USERDATA":
        raise RuntimeError("--execute requires --confirm ERASE_CORAL_USERDATA")
    ensure_mac()
    source=source.expanduser().resolve(strict=True)
    output=fresh_folder(output)
    if source.suffix!=".sparseimage":
        raise RuntimeError("Expected existing Mac-made iOS sparseimage")
    if not 1_000_000_000 <= source.stat().st_size <= 50_000_000_000:
        raise RuntimeError("Unexpected input image size")
    if not isinstance(run_id,int) or run_id<=0:
        raise RuntimeError("A successful pinned GitHub run ID is required")
    # The root exporter requires a large local HFS partition; verify free
    # space BEFORE making a source checkout or touching the user's phone.
    free=shutil.disk_usage(output.parent).free
    if free<32*1024**3:
        raise RuntimeError("Insufficient Mac disk space; need at least 32 GiB free")
    output.mkdir(mode=0o700)
    upstream=output/"pinned-ios-flame"
    tweaks=source_checkout(upstream)
    boot_dir=output/"boot"
    boot_dir.mkdir()
    command(["gh","run","download",str(run_id),"-R",REPO,
             "-n",ARTIFACT,"-D",boot_dir])
    boot=checked_boot_img(boot_dir)
    raw_dir=output/"root"
    command([sys.executable,
             Path(__file__).with_name("finalize_ios_root.py"),
             source,tweaks,raw_dir,"--execute"])
    raw=raw_dir/"CoralIOSRoot-final.img"
    if not raw.is_file():
        raise RuntimeError("No final raw HFS+ image; nothing has been installed")
    from deploy_ios_root import raw_info
    _,check=raw_info(raw)
    print("Raw HFS+ ready, bytes:",check["bytes"],flush=True)
    # Boot user-supplied Coral recovery if given, otherwise require the
    # already connected device be in rooted, UNMOUNTED recovery.
    if recovery:
        recovery=recovery.expanduser().resolve(strict=True)
        if not recovery.is_file() or recovery.suffix!=".img":
            raise RuntimeError("Recovery image must be a local .img file")
        subprocess.run(["adb","reboot","bootloader"],check=True)
        fastboot_coral()
        command(["fastboot","boot",recovery])
        command(["adb","wait-for-device"])
    # All identity, root, unmounted-data, PARTNAME and partition-size
    # checks happen again immediately before the only destructive write.
    from deploy_ios_root import install
    install(raw,output/"private-device-backups","ERASE_CORAL_USERDATA")
    # The new firmware boots through Google's ABL, with no boot slot flash.
    command(["adb","reboot","bootloader"])
    fastboot_coral()
    command(["fastboot","boot",boot])
    print("EXPERIMENTAL full-iOS launch attempted. PHYSICAL SpringBoard outcome UNKNOWN.")
    print("Keep a camera recording the screen and the PRIVATE calibration backups.")
    return boot

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,
                   default=Path.home()/"Coral-iOS-16-work/CoralIOSRoot.sparseimage")
    p.add_argument("--output",type=Path,
                   default=Path.home()/"Coral-iOS-16-complete")
    p.add_argument("--run-id",type=int,required=True,
                   help="successful UFS-root artifact GitHub Actions run number")
    p.add_argument("--recovery",type=Path,
                   help="optional local Pixel 4 XL TWRP recovery .img")
    p.add_argument("--execute",action="store_true")
    p.add_argument("--confirm",default="")
    a=p.parse_args()
    if not a.execute:
        print(json.dumps({
            "mode":"PLAN ONLY — phone and files unchanged",
            "device":"coral",
            "source":str(a.source),
            "output":str(a.output),
            "github_ufs_boot_run":a.run_id,
            "recovery":str(a.recovery) if a.recovery else "already rooted TWRP required",
            "danger":"--execute erases userdata after calibration backups and attempts real iOS boot",
            "full_ios_springboard_hardware_proven":False,
            "required_confirmation":"ERASE_CORAL_USERDATA",
        },indent=2))
        return
    try:
        execute(a.source,a.output,a.run_id,a.recovery,a.confirm)
    except (RuntimeError,OSError,subprocess.CalledProcessError,ValueError) as e:
        p.error(str(e))

if __name__=="__main__":
    main()
