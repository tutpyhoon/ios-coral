#!/usr/bin/env python3
"""Consistency checks for measured CORAL boot hardware evidence.

This is a host-side *metadata* check. It never touches a device, produces no
boot image, and cannot establish that a kernel handoff is safe. Any future
bootloader must revalidate the live FDT, runtime memory ownership, and CPU state.
"""
import json
from pathlib import Path


def number(value):
    return int(value, 16) if isinstance(value, str) else int(value)


def within(base, size, outer_base, outer_size):
    return size > 0 and outer_size > 0 and outer_base <= base and (
        base + size <= outer_base + outer_size
    )


def overlaps(a, n, b, m):
    return a < b + m and b < a + n


def check(observations):
    p1 = observations["probe01"]
    p2 = observations["probe02"]
    p3 = observations["probe03"]
    p4 = observations["probe04"]

    banks = [(number(b["base"]), number(b["size"])) for b in p1["ram_banks"]]
    assert len(banks) == p2["ram_banks"] == 2
    assert all(size > 0 for _, size in banks)
    assert all(not overlaps(a, n, b, m) for i, (a, n) in enumerate(banks)
               for b, m in banks[i + 1:])

    candidate, length = number(p2["candidate_base"]), number(p2["candidate_size"])
    assert (candidate, length) == (0x100000000, 0x40000000)
    assert p2["in_ram"] and any(within(candidate, length, b, s) for b, s in banks)
    assert p2["conflicts"] == p2["map_errors"] == p2["unbounded_pools"] == 0
    assert not p2["accessed_candidate_ram"]

    fdt, fdt_size = number(p1["fdt_base"]), number(p1["fdt_total_size"])
    splash, reserve = number(p1["splash_base"]), number(p1["splash_reserved_size"])
    assert fdt_size > 0 and reserve > 0
    assert any(within(fdt, fdt_size, b, s) for b, s in banks)
    assert any(within(splash, reserve, b, s) for b, s in banks)
    assert not overlaps(fdt, fdt_size, candidate, length)
    assert not overlaps(splash, reserve, candidate, length)
    assert not overlaps(fdt, fdt_size, splash, reserve)

    width, height = p1["drawn_width_px"], p1["drawn_height_px"]
    assert (width, height) == (1440, 3040)
    assert width * height * 4 <= reserve
    # Contiguous probe writes do NOT prove a hardware display pitch.
    assert p1["current_el"] == 1
    assert number(p1["mpidr_el1"]) & 0xffffff == 0
    assert p1["tgran16_field"] == 1
    assert p1["cntfrq_el0_hz"] == 19_200_000
    assert number(p1["psci_version"]) == 0x00010001

    page = p3["page_size_bytes"]
    first, last = number(p3["first_page"]), number(p3["last_page"])
    assert page == 0x4000 and candidate % page == length % page == 0
    assert first == candidate and last == candidate + length - page
    assert p3["words_compared"] == 2 * (2 * page // 8)
    assert p3["pattern_errors"] == p3["restore_errors"] == 0
    assert not p3["tested_entire_candidate"]
    assert p4["translations_verified"] and p4["translated_two_page_test_passed"]
    assert p4["pattern_errors"] == p4["restore_errors"] == 0
    assert p4["sctlr_restored_reported"] and p4["mmu_disabled_again_reported"]
    assert p1["no_partition_writes_reported"] and p4["no_partition_writes_reported"]
    assert observations["user_confirmed_normal_android_restart_after_probes"] == [1, 2, 3, 4]
    print("PASS: photographed Coral 01–04 evidence is internally consistent")
    print("NOT CLEARED: kernel handoff and full RAM ownership still require live checks")


if __name__ == "__main__":
    check(json.loads(Path(__file__).with_name("hardware_observations.json").read_text()))
