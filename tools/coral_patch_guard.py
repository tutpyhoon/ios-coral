#!/usr/bin/env python3
"""Phase 22: fail-closed CORAL patch guard for the *pinned* dxb XNU builder.

Run against only the temporary GitHub Actions dxb/build.sh checkout; it never
runs the builder, mutates an XNU checkout, or interacts with any phone.
"""
from pathlib import Path
import argparse
import re
import sys

TAG = '# CORAL_PHASE21_PATCH_APPLICATION_GUARD'
# Check that patch loop and function boundary are those of the pinned dxb helper;
# allow its actual blank line between the closing brace and next function.
PATCH_LOOP = 'for PATCH in "${PATCH_DIR}"/*.patch; do'
PATCH_CHECK = 'if APPLY_CHECK=$(git apply --check "$PATCH" 2>&1); then'
BOUNDARY = re.compile(
    r'(?m)^        cd "\$\{WORK_DIR\}"\r?\n'
    r'    fi\r?\n'
    r'}\r?\n(?:\r?\n)*'
    r'build_bootstrap_cmds\(\) \{'
)

CHECK = '''        {tag}
        if [[ "${{MACHINE_CONFIG}}" == "CORAL" ]]; then
            local coral_tree="${{WORK_DIR}}/xnu"
            if [[ ! -s "${{coral_tree}}/pexpert/pexpert/arm64/CORAL.h" ||
                  ! -s "${{coral_tree}}/iokit/Kernel/arm/CoralCPU.cpp" ||
                  ! -s "${{coral_tree}}/iokit/Kernel/arm/CoralPlatformExpert.cpp" ]]; then
                error "CORAL 0082 patch missing; build aborted"
                exit 1
            fi
            if ! grep -Eq '^SUPPORTED_ARM64_MACHINE_CONFIGS[[:space:]]*=.*CORAL' "${{coral_tree}}/makedefs/MakeInc.def"; then
                error "CORAL machine configuration missing; build aborted"
                exit 1
            fi
            if ! grep -q 'ARM64_BOARD_CONFIG_CORAL' "${{coral_tree}}/pexpert/pexpert/arm64/board_config.h"; then
                error "CORAL board configuration missing; build aborted"
                exit 1
            fi
            if ! grep -q 'CoralPlatformExpert' "${{coral_tree}}/iokit/KernelConfigTables.cpp"; then
                error "CORAL platform matching missing; build aborted"
                exit 1
            fi
            if ! git -C "${{coral_tree}}" diff --check; then
                error "XNU patch stack introduces whitespace errors; build aborted"
                exit 1
            fi
            info "CORAL 0082 foundation present; starting real XNU compile"
        fi
'''.format(tag=TAG)


def patch_script(data: str) -> str:
    if data.count(TAG):
        if data.count(TAG) != 1 or CHECK not in data:
            raise ValueError('existing CORAL patch guard differs; refusing to overwrite')
        return data
    if data.count(PATCH_LOOP) != 1 or data.count(PATCH_CHECK) != 1:
        raise ValueError('pinned builder patch loop changed; refusing unsafe insertion')
    matches = list(BOUNDARY.finditer(data))
    if len(matches) != 1:
        raise ValueError('expected pinned patch-function boundary not found exactly once')
    m = matches[0]
    # Require the selected boundary to occur *after* the patch loop.
    if m.start() < data.index(PATCH_LOOP) or m.start() < data.index(PATCH_CHECK):
        raise ValueError('selected guard location precedes XNU patch application')
    original = m.group(0)
    return data[:m.start()] + CHECK + original + data[m.end():]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('build_script', type=Path)
    args = ap.parse_args()
    try:
        p = args.build_script.resolve()
        old = p.read_text()
        new = patch_script(old)
        if new != old:
            p.write_text(new)
        print('PASS CORAL patch guard installed in temporary dxb build script')
        print('NOTE: this does not build XNU or enable hardware boot')
        return 0
    except (OSError, ValueError) as exc:
        print(f'STOP: {exc}', file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
