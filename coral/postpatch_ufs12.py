#!/usr/bin/env python3
"""After applying the pinned patches, preserve proven CORAL viewport geometry
and assert the *OPTIONAL* read-only UFS driver was built into the XNU tree.
Never activate UFS boot; no storage writes or root mount here.
"""
from pathlib import Path
import sys

def once(path,old,new):
    text=path.read_text()
    if text.count(old)!=1:
        raise SystemExit(f"STOP: {path} expected once {old!r}, got {text.count(old)}")
    path.write_text(text.replace(old,new))

def check(root):
    start=root/"osfmk/arm64/start.s"
    early=root/"osfmk/arm64/sweet_early.c"
    once(start,"\tmov\t\tx4, #4320","\tmov\t\tx4, #5760")
    once(early,"#define EARLY_WIDTH 1080u","#define EARLY_WIDTH 1440u")
    once(early,"#define EARLY_STRIDE (4320u / 4)","#define EARLY_STRIDE (5760u / 4)")
    expect={
        start:["0x9c400000 + 3008 * 5760","1440 * 3040 * 4","x4, #5760"],
        early:["#define EARLY_WIDTH 1440u","#define EARLY_HEIGHT 3040u",
               "#define EARLY_STRIDE (5760u / 4)"],
        root/"iokit/KernelConfigTables.cpp":["'google,coral'"],
        root/"bsd/dev/sweet_ufs.c":[
            "SWEET internal UFS root device (read-only)",
            "Writes are refused.",
            "ufs_read_blocks(",
            "return (flags & FWRITE) ? EROFS : 0;",
            'SecureDTLookupEntry(NULL, "/sweet-ufs", &node)',
        ],
        root/"iokit/bsddev/IOKitBSDInit.cpp":[
            'strcmp(rdBootVar, "ufsroot0")',
            "sweet_ufs_rootdev(root)",
        ],
        root/"osfmk/arm64/arm_vm_init.c":["1440 * 3040 * 4","flame_fb_l3"],
    }
    for file,tokens in expect.items():
        if not file.is_file():
            raise SystemExit(f"STOP: missing {file}")
        text=file.read_text()
        for token in tokens:
            if token not in text:
                raise SystemExit(f"STOP: missing {token!r} in {file}")
    ufs=(root/"bsd/dev/sweet_ufs.c").read_text()
    for token in ["ufs_write_blocks(", "ufsrw", "0x2a, 0,", "writeback"]:
        if token in ufs:
            raise SystemExit(f"STOP: write-capable driver token {token!r}")
    print("PASS: Coral XNU display/identity retained and UFS 0028 read-only source present")
    print("UFS NOT ACTIVE: requires rd=ufsroot0 and /sweet-ufs ADT node (not supplied).")

if __name__=="__main__":
    if len(sys.argv)!=2:
        raise SystemExit("Usage: postpatch_ufs12.py PATH_TO_PATCHED_XNU")
    check(Path(sys.argv[1]).resolve())
