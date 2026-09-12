"""Reproduce builds using only Git-visible source files, excluding local artifacts."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]


def main():
    clean=Path(tempfile.mkdtemp(prefix='cloud-clean-source-',dir='/srv'))
    files=subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT).decode().split('\0')
    for relative in set(filter(None,files)):
        source=ROOT/relative
        if not source.is_file():
            continue
        if source.name=='.env' or any(part in {'.git','node_modules','artifacts','__pycache__'} for part in source.relative_to(ROOT).parts):
            raise RuntimeError('Private or generated input unexpectedly visible to Git')
        destination=clean/relative
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
    # Does not rely on any virtual environment, frontend build, or image archive
    # from the original checkout. Docker's immutable image cache is reusable.
    report={'source':str(clean),'result':'running'}
    try:
        subprocess.run(['bash','scripts/build-from-source.sh'],cwd=clean,check=True)
        report['result']='passed'
    finally:
        output=ROOT/'artifacts/release/clean-source-verification.json'
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':
    main()
