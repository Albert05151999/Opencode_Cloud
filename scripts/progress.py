"""Record a phase start or MainAgent verification result."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('task')
parser.add_argument('status', choices=['running', 'completed', 'blocked'])
parser.add_argument('--command', required=True)
parser.add_argument('--result', default='pending')
parser.add_argument('--files', nargs='+', required=True)
parser.add_argument('--next')
parser.add_argument('--limitations', default='None recorded')
parser.add_argument('--json-only', action='store_true', help='Defer checklist edits while another task owns the document')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
path = root / 'docs/progress.json'
data = json.loads(path.read_text(encoding='utf-8-sig'))
task = next((t for t in data['tasks'] if t['id'] == args.task), None)
if task is None:
    task = {'id': args.task}
    data['tasks'].append(task)
task.update(status=args.status, owner='MainAgent', expected_outputs=args.files,
            files_changed=args.files, verification_command=args.command,
            observed_output=args.result, pass_fail='passed' if args.status == 'completed' else args.result,
            known_limitations=[args.limitations], next_task_unlocked=args.next)
data['current_task'] = args.next or args.task
path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')
if args.status == 'completed' and not args.json_only:
    todo = root / '03_zero_to_one_todolist.md'
    text = todo.read_text(encoding='utf-8')
    start = text.index(f'# {args.task}. ')
    end = text.find('\n# ', start + 1)
    if end == -1:
        end = len(text)
    text = text[:start] + text[start:end].replace('- [ ]', '- [x]') + text[end:]
    todo.write_text(text, encoding='utf-8')
