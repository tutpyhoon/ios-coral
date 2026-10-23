#!/usr/bin/env python3
"""Symbolicate ARM64 Mach-O kernel addresses using LC_SYMTAB, stdlib only.

Offline host-only diagnostic. Reads a built XNU file, never executes it.
Usage: python3 coral/symbolicate_macho.py kernel.development.sweet 0xfffffe...
"""
import argparse
import bisect
import json
from pathlib import Path
import struct

def symbols(path):
    data=Path(path).read_bytes()
    if len(data)<32 or struct.unpack_from("<I",data,0)[0]!=0xfeedfacf:
        raise ValueError("expected little endian Mach-O 64")
    magic,cputype,subtype,kind,ncmds,cmdsize,flags,reserved=struct.unpack_from("<8I",data,0)
    if cputype != 0x0100000c or ncmds>4096 or 32+cmdsize>len(data):
        raise ValueError("expected ARM64 kernel Mach-O with sane load commands")
    off=32
    symtab=None
    for i in range(ncmds):
        if off+8>len(data):
            raise ValueError("truncated load commands")
        cmd,size=struct.unpack_from("<2I",data,off)
        if size<8 or off+size>32+cmdsize:
            raise ValueError("invalid load command")
        if cmd==2:
            if size<24:
                raise ValueError("short LC_SYMTAB")
            symtab=struct.unpack_from("<4I",data,off+8)
        off+=size
    if symtab is None:
        raise ValueError("kernel lacks LC_SYMTAB")
    symoff,nsyms,stroff,strsize=symtab
    if nsyms>2_000_000 or symoff+nsyms*16>len(data) or stroff+strsize>len(data):
        raise ValueError("invalid symbol/string table")
    found=[]
    for i in range(nsyms):
        strx,ntype,sect,desc,value=struct.unpack_from("<IBBHQ",data,symoff+i*16)
        if not (ntype & 0x0e)==0x0e or value==0 or strx>=strsize:
            continue
        start=stroff+strx
        end=data.find(b"\x00",start,stroff+strsize)
        if end<0:
            continue
        name=data[start:end].decode("utf-8","replace")
        found.append((value,name))
    found.sort()
    return found

def nearest(found,pc):
    points=[x[0] for x in found]
    idx=bisect.bisect_right(points,pc)-1
    if idx<0:
        return {"pc":hex(pc),"nearest":None}
    value,name=found[idx]
    ahead=found[idx+1][0] if idx+1<len(found) else None
    return {"pc":hex(pc),"symbol":name,"symbol_addr":hex(value),
            "offset_bytes":pc-value,
            "next_symbol_addr":hex(ahead) if ahead is not None else None,
            "within_next_symbol":ahead is None or pc<ahead}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("kernel",type=Path)
    p.add_argument("addresses",nargs="+",help="PC/LR/caller in hex")
    a=p.parse_args()
    values=symbols(a.kernel)
    print(json.dumps({"kernel":str(a.kernel),"symbols":len(values),
                      "hits":[nearest(values,int(x,0)) for x in a.addresses]},indent=2))

if __name__=="__main__":
    main()
