"""Compatibility handoff for the immutable first offline bundle; no files are patched."""
import argparse
from pathlib import Path
import shlex
import subprocess
import sys

from verify_loaded_image import verify


def patched_script(root, helper):
    root, helper = Path(root), Path(helper)
    if not root.is_absolute() or not helper.is_absolute():
        raise ValueError('Use absolute paths')
    text = (root / 'install_offline.sh').read_text(encoding='utf-8')
    lines = text.splitlines()
    root_indexes = [i for i, line in enumerate(lines) if line.startswith('ROOT=')]
    check_indexes = [i for i, line in enumerate(lines) if '|| fail \'Loaded base image identity mismatch.\'' in line]
    if len(root_indexes) != 1 or len(check_indexes) != 1:
        raise ValueError('Unexpected installer version; no compatibility substitution made')
    lines[root_indexes[0]] = 'ROOT=' + shlex.quote(str(root))
    lines[check_indexes[0]] = '    python3 ' + shlex.quote(str(helper)) + ' "$ROOT"'
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bundle', required=True)
    args = parser.parse_args()
    root = Path(args.bundle)
    subprocess.run([sys.executable, str(root / 'verify_offline_bundle.py'), str(root)], check=True)
    print(verify(root), flush=True)
    helper = Path(__file__).resolve().with_name('verify_loaded_image.py')
    script = patched_script(root, helper)
    # The verified bundle stays byte-for-byte unchanged. bash receives the script on stdin.
    result = subprocess.run(['bash', '-s', '--', 'prepare'], input=script, text=True, cwd=root)
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
