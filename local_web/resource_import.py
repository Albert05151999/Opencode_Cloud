"""Collect explicitly selected local OpenCode configuration and real Skill files."""
import io
import json
import zipfile
from pathlib import Path

from app.management import fail
from app.transfers import FORMAT, LIMIT, parse_native, skill_item
from local_web.importer import jsonc


def collect(importer, file, include_external_skills=False):
    if not isinstance(file, str) or not file.strip():
        fail('Select a local OpenCode configuration file')
    requested = Path(file).expanduser().resolve()
    sources = [s for s in importer.discover(file=file)['sources'] if importer.sources[s['id']] == requested]
    if len(sources) != 1:
        fail('Select one OpenCode configuration file')
    source = importer.sources[sources[0]['id']]
    raw = jsonc(source.read_text(encoding='utf-8-sig'))
    # Resolve only configuration values; file payloads below remain byte-exact.
    config = importer.resolve_value({k: v for k, v in raw.items() if k in {'mcp', 'model', 'small_model'}}, source.parent)
    items, warnings = parse_native(config)
    if raw.get('provider'):
        preview = importer.preview(sources[0]['id'])
        if preview['errors']:
            fail('Model import errors: ' + '; '.join(str(e.get('error')) for e in preview['errors']))
        models = importer.take(preview['preview_id'], [m['id'] for m in preview['models']])
        items.extend({'id': m['id'], 'kind': 'model', 'name': m.get('name', m['id']), 'data': m} for m in models)
    if not isinstance(raw.get('skills', {}), dict):
        fail('skills must be a configuration object')
    paths = raw.get('skills', {}).get('paths', [])
    if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
        fail('skills.paths must be a list of directories')
    paths = paths + ['skills', '.opencode/skills']
    seen, total = set(), 0
    for declared in paths:
        path = Path(declared).expanduser()
        path = path if path.is_absolute() else source.parent / path
        if not path.exists():
            if declared not in {'skills', '.opencode/skills'}:
                warnings.append('Skill path is missing: ' + declared)
            continue
        if path.is_symlink():
            fail('Skill directory links are not supported')
        resolved = path.resolve()
        if not resolved.is_relative_to(source.parent.resolve()) and not include_external_skills:
            fail('Skill path is outside the configuration directory; explicitly enable external Skill paths')
        roots = [path] if (path / 'SKILL.md').is_file() else [p.parent for p in path.glob('*/SKILL.md')]
        for root in roots:
            if root.is_symlink() or not root.resolve().is_relative_to(resolved):
                fail('Skill directory links are not supported')
            if root.resolve() in seen:
                continue
            seen.add(root.resolve())
            if len(seen) > 100:
                fail('At most 100 Skills per local import')
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w', zipfile.ZIP_STORED) as archive:
                count = 0
                for entry in root.rglob('*'):
                    if entry.is_symlink():
                        fail('Skill file links are not supported')
                    if not entry.is_file():
                        continue
                    count += 1
                    total += entry.stat().st_size
                    if count > 1000 or total > LIMIT // 2:
                        fail('Local Skill collection exceeds the transfer limit', 413)
                    archive.writestr(entry.relative_to(root).as_posix(), entry.read_bytes())
            items.append(skill_item('skill.zip', stream.getvalue()))
    result = json.dumps({'format': FORMAT, 'format_version': 1, 'items': items, 'warnings': warnings}).encode()
    if len(result) > LIMIT:
        fail('Collected configuration exceeds 20 MiB', 413)
    return result
