"""Read every archived regular file and record a recovery checksum without extracting."""
import hashlib
import json
from pathlib import Path
import tarfile

path = Path(__file__).resolve().parents[1] / 'artifacts/env/backups/Ubuntu-24.04-before-reset.tar'
count = 0
data_bytes = 0
required = {'etc/passwd', 'usr/lib/os-release', 'home/zephyrusg14'}
with tarfile.open(path, 'r:') as archive:
    for member in archive:
        required.discard(member.name.removeprefix('./').rstrip('/'))
        count += 1
        if member.isfile():
            stream = archive.extractfile(member)
            size = 0
            while chunk := stream.read(1024 * 1024):
                size += len(chunk)
            if size != member.size:
                raise RuntimeError(f'Truncated archive member: {member.name}')
            data_bytes += size
if required:
    raise RuntimeError(f'Missing required entries: {required}')
with path.open('rb') as stream:
    digest = hashlib.file_digest(stream, 'sha256').hexdigest()
result = dict(path=str(path), size_bytes=path.stat().st_size, sha256=digest,
              members=count, verified_regular_file_bytes=data_bytes, result='passed',
              limitation='Archive read verification; a restore boot test has not been performed.')
path.with_suffix('.verification.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, indent=2))
