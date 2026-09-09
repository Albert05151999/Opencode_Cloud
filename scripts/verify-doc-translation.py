"""Compare structural invariants with the pre-translation snapshots."""
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
results = []
for name in ['01_architecture.md', '02_api_contract.md', '03_zero_to_one_todolist.md']:
    before = (root / 'artifacts/docs-review' / name).read_text(encoding='utf-8')
    after = (root / name).read_text(encoding='utf-8')
    if name == '03_zero_to_one_todolist.md':
        progress = json.loads((root / 'docs/progress.json').read_text(encoding='utf-8'))
        for task in progress['tasks']:
            marker = f"# {task['id']}. "
            if task['status'] != 'completed' or marker not in before:
                continue
            start = before.index(marker)
            end = before.find('\n# ', start + 1)
            if end == -1:
                end = len(before)
            before = before[:start] + before[start:end].replace('- [ ]', '- [x]') + before[end:]
    checks = {
        'code_blocks': re.findall(r'```.*?```', before, re.S) == re.findall(r'```.*?```', after, re.S),
        'checkbox_states': re.findall(r'- \[([ x])\]', before) == re.findall(r'- \[([ x])\]', after),
        'numbered_headings': re.findall(r'^#+ (\d+(?:\.\d+)*)(?:\.|\s)', before, re.M) == re.findall(r'^#+ (\d+(?:\.\d+)*)(?:\.|\s)', after, re.M),
        'contains_chinese': len(re.findall(r'[\u4e00-\u9fff]', after)) > 100,
    }
    results.append({'file': name, 'checks': checks})
report = {'result': 'passed' if all(all(x['checks'].values()) for x in results) else 'failed', 'files': results,
          'limitation': 'Structural checks supplement MainAgent semantic review; they do not prove translation accuracy.'}
(root / 'artifacts/docs-review/verification.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
if report['result'] != 'passed':
    raise SystemExit(1)
