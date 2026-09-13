#!/usr/bin/env python3
"""Collect executable deployment scripts, independently of server image builds."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]

def export_scripts(root=ROOT):
    root = Path(root)
    for kind, sources in {
        'server': [root / 'build_image/bundle', root / 'build_image/docker'],
        'admin_web': [root / 'admin_web/scripts'],
    }.items():
        output = root / 'artifacts/scripts' / kind
        output.mkdir(parents=True, exist_ok=True)
        for directory in sources:
            for source in directory.glob('*.sh'):
                target = output / source.name
                shutil.copy2(source, target)
                target.chmod(0o755)

if __name__ == '__main__': export_scripts()
