#!/usr/bin/env python3
"""Build cautious, temporary Pixel 4 XL hardware probes from a pinned Pixel 4 port.

This does NOT package an iOS root, flash a partition, or claim that XNU boots.
The upstream loader, FDT validation, and Pixel kernel tooling remain at a
recorded commit so any upstream changes require deliberate review.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "coral" / "_flame_source"
OUT = ROOT / "coral" / "out"
FLAME_REPO = "https://github.com/dimasmds/ios-flame.git"
FLAME_SHA = "b91463ab1ef083f81f6c3393593385aa996ceaf0"


def command(*args: str, cwd: Path | None = None) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=cwd, check=True)


def replace_unique(path: Path, old: str, new: str, *, count: int = 1) -> None:
    contents = path.read_text()
    observed = contents.count(old)
    if observed != count:
        raise RuntimeError(f"{path}: expected {count} occurrences of {old!r}, found {observed}")
    path.write_text(contents.replace(old, new))


def build() -> None:
    if WORK.exists():
        raise SystemExit(
            "Refusing to reuse or overwrite coral/_flame_source. "
            "Remove that generated directory to rebuild from a clean pinned source."
        )
    WORK.mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    command("git", "init", "-q", str(WORK))
    command("git", "fetch", "-q", "--depth=1", FLAME_REPO, FLAME_SHA, cwd=WORK)
    command("git", "checkout", "-q", "--detach", "FETCH_HEAD", cwd=WORK)
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=WORK, text=True
    ).strip()
    if actual != FLAME_SHA:
        raise RuntimeError(f"Unexpected source revision: {actual}")

    # Pixel 4 (flame) and 4 XL (coral) share Google's SM8150 boot-source
    # family, but the physical framebuffer dimensions differ. The original
    # probe's live-FDT reservation and bounds checks must remain in force.
    probe = WORK / "flame" / "probe.c"
    replace_unique(probe, "#define WIDTH 1080U", "#define WIDTH 1440U")
    replace_unique(probe, "#define HEIGHT 2280U", "#define HEIGHT 3040U")
    src = probe.read_text()
    original_labels = src.count("PIXEL 4 / FLAME")
    if original_labels < 5:
        raise RuntimeError("Pixel diagnostic source changed; refusing label rewrite")
    probe.write_text(src.replace("PIXEL 4 / FLAME", "PIXEL 4 XL / CORAL"))

    # This is an experimental unsigned image for an already-unlocked phone.
    # Do not impersonate a Google-signed production image.
    builder = WORK / "flame" / "build.sh"
    replace_unique(builder, "experimental/flame/flame", "experimental/coral/coral")
    replace_unique(builder, "666c616d652d70726f62652d3031", "636f72616c2d70726f62652d3031")

    command(sys.executable, "flame/fetch.py", cwd=WORK)
    manifest = {
        "target": "Google Pixel 4 XL (coral)",
        "upstream": FLAME_REPO,
        "upstream_sha": FLAME_SHA,
        "purpose": "temporary boot diagnostics; no storage writes",
        "images": [],
    }
    for mode in ("01", "02"):
        command("bash", "flame/build.sh", mode, cwd=WORK)
        command(sys.executable, "flame/check.py", mode, cwd=WORK)
        built = WORK / "flame" / "out" / f"flame-probe-{mode}.img"
        dest = OUT / f"coral-probe-{mode}.img"
        shutil.copyfile(built, dest)
        manifest["images"].append({
            "file": dest.name,
            "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
            "bytes": dest.stat().st_size,
            "mode": "CPU/FDT/splash" if mode == "01" else "read-only RAM map",
        })
        print(f"BUILT {dest}: {manifest['images'][-1]['sha256']}", flush=True)

    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("Host validation complete. Nothing was flashed and no device was contacted.")


if __name__ == "__main__":
    try:
        build()
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        raise SystemExit(f"STOP: {exc}") from exc
