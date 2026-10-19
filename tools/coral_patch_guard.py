#!/usr/bin/env python3
"""Pin dxb's patch loop to an explicit, fail-closed CORAL source check.

This script changes only the temporary GitHub Actions checkout of dxb/build.sh.
It does not build, link, flash, or access the phone.
"""
import argparse
from pathlib import Path
import sys

TAG = '# CORAL_PHASE21_PATCH_APPLICATION_GUARD'
ANCHOR = '        cd "${WORK_DIR}"\n    fi\n}\nbuild_bootstrap_cmds() {'
CHECK = '''        {tag}
        if [[ "${{MACHINE_CONFIG}}" == "CORAL" ]]; then
            local coral_tree="${{WORK_DIR}}/xnu"
            if [[ ! -s "${{coral_tree}}/pexpert/pexpert/arm64/CORAL.h" ||
                  ! -s "${{coral_tree}}/iokit/Kernel/arm/CoralCPU.cpp" ||
                  ! -s "${{coral_tree}}/iokit/Kernel/arm/CoralPlatformExpert.cpp" ]]; then
                error "CORAL 0082 patch missing; build aborted (the upstream builder may silently skip patches)"
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
            if ! git -C "${{coral_tree}}" diff --check; then
                error "XNU patch stack introduces whitespace errors; build aborted"
                exit 1
            fi
            info "CORAL foundation applied; beginning actual XNU build"
        fi
'''.format(tag=TAG)


def patch_script(data: str) -> str:
    if TAG in data:
        if CHECK not in data:
            raise ValueError('existing phase21 guard has unexpected content')
        return data
    if data.count(ANCHOR) != 1:
        raise ValueError('pinned dxb patch function anchor not found exactly once')
    return data.replace(ANCHOR, CHECK + ANCHOR, 1)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('build_script', type=Path)
    a = p.parse_args()
    path = a.build_script.resolve()
    original = path.read_text()
    try:
        updated = patch_script(original)
    except ValueError as exc:
        print('STOP:', exc, file=sys.stderr)
        return 2
    if updated != original:
        path.write_text(updated)
        print('PASS pinned XNU builder now requires applied Coral XNU foundation')
    else:
        print('PASS guard already installed')
    print('NOTE actual XNU compilation has not yet occurred')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
