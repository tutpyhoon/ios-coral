#!/usr/bin/env python3
"""EXPERIMENTAL CORAL USERDATA-only writable-root XNU overlay.

Apply only AFTER port_flame_full_xnu.py's three unconditional write fences
have passed and ONLY in a separate compilation-only build. No phone image
is built by this script.

Design: double opt-in (ufsrw=1 AND coraluserdatawrite=1) AND verified GPT
PARTNAME="userdata". Original upstream ufs_write_blocks has a second strict
bounds fence su.first_block..su.nblocks that is retained unchanged.
No other named partition can be selected for media WRITE(10).
This code is not physically tested on CORAL; it must NOT be used to create
an installable boot image before read-only XNU GPT proof and data backups.
"""
import argparse
from pathlib import Path


def exact(path, before, after):
    source=path.read_text()
    if source.count(before)!=1:
        raise ValueError(f"Unexpected upstream source in {path}: {before[:90]!r} count={source.count(before)}")
    path.write_text(source.replace(before,after))


def prepare(root):
    root=Path(root).expanduser().resolve(strict=True)
    source=root/"bsd/dev/sweet_ufs.c"
    if not source.is_file():
        raise ValueError("Expected full Flame kernel with the CORAL read-only overlay")
    original=source.read_text()
    required=[
        "CORAL_MEDIA_WRITE_FENCE",
        "su.writable = false;",
        "ufs_write_blocks(uint64_t lba, uint32_t count)",
        "lba < su.first_block",
        "count > su.nblocks - (lba - su.first_block)",
        'PE_parse_boot_argn("ufsrw", &rw, sizeof(rw));',
        'PE_parse_boot_argn("ufsroot", want, sizeof(want));',
    ]
    for token in required:
        if token not in original:
            raise ValueError(f"Storage write safety requirement missing: {token}")
    exact(source,
          "    /* CORAL_MEDIA_WRITE_FENCE: never submit device write or erase. */\n"
          "    if (write || (cdb_len && (cdb[0] == 0x2a || cdb[0] == 0xaa ||\n"
          "                              cdb[0] == 0x35 || cdb[0] == 0x42)))\n"
          "        return EROFS;",
          "    /* CORAL_WRITABLE_PROFILE: all write-like CDBs require the\n"
          "     * separately gated, GPT-checked userdata-only writable state.\n"
          "     */\n"
          "    if ((write || (cdb_len && (cdb[0] == 0x2a || cdb[0] == 0xaa ||\n"
          "                                cdb[0] == 0x35 || cdb[0] == 0x42))) &&\n"
          "        !su.writable)\n"
          "        return EROFS;")
    exact(source,
          "    /* CORAL_MEDIA_WRITE_FENCE: block direct WRITE(10) helper use. */\n"
          "    return EROFS;",
          "    /* CORAL_WRITABLE_PROFILE: still check the upstream GPT bounds. */\n"
          "    if (!su.writable) return EROFS;")
    exact(source,
          "su.writable = false; /* CORAL_MEDIA_WRITE_FENCE: ignore ufsrw */",
          'uint32_t coral_userdata_write = 0;\n'
          '    (void)PE_parse_boot_argn("coraluserdatawrite", &coral_userdata_write,\n'
          '                             sizeof(coral_userdata_write));\n'
          '    su.writable = (rw == 1 && coral_userdata_write == 1 &&\n'
          '                   strcmp(want, "userdata") == 0);\n'
          '    printf("CORAL UFS: userdata-only write permission %s\\\\n",\n'
          '           su.writable ? "explicitly ENABLED" : "DENIED");')
    updated=source.read_text()
    # Never accept modifications that remove the partition boundary guard,
    # which is the last line of defense in the existing upstream driver.
    for marker in ("lba < su.first_block",
                   "count > su.nblocks - (lba - su.first_block)",
                   "su.writable = (rw == 1 && coral_userdata_write == 1",
                   'strcmp(want, "userdata") == 0',
                   'PE_parse_boot_argn("coraluserdatawrite"',
                   "CORAL_WRITABLE_PROFILE"):
        if marker not in updated:
            raise ValueError("Write-profile guard missing: "+marker)
    if "su.writable = true;" in updated:
        raise ValueError("Unconditional UFS writes are forbidden")
    print("PASS: optional userdata-only UFS write profile staged for HOST COMPILATION")
    print("No boot image. No phone operation. Still needs real physical UFS GPT verification.")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("patched_xnu_source",type=Path)
    prepare(parser.parse_args().patched_xnu_source)
