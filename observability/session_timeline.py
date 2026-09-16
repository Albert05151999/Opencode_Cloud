"""Session execution history from recorded events, without inferred parent spans."""
import re
from datetime import datetime, timezone, timedelta


def session_timeline(events, limit=50):
    def instant(value):
        try:
            result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
        except (ValueError, TypeError):
            return None

    def request(event):
        return (event.get('module') == 'api_gateway' and event.get('method') == 'POST'
                and re.fullmatch(r'/session/[^/]+/(?:message|prompt_async|command|shell)', event.get('path', '')))

    # Link only explicit trace/message identities; never assign by nearest time.
    aliases = {}
    for event in events:
        mid, tid = event.get('message_id'), event.get('trace_id')
        if mid and tid and (request(event) or event.get('action') == 'model_dispatch'
                            or event.get('module') == 'model_gateway'):
            aliases.setdefault(mid, tid)
    groups = {}
    for index, event in enumerate(events):
        action, module = event.get('action'), event.get('module')
        kind = ('request' if request(event) else
                'runtime_scope' if module == 'agent_runtime' and action in {'runtime_complete','runtime_error'} else
                'runtime' if module == 'agent_runtime' and action == 'model_dispatch' else
                'tool' if module == 'agent_runtime' and action in {'tool_complete', 'tool_error'} else
                'model_phase' if module == 'model_gateway' and action == 'stage_complete' else
                'model' if module == 'model_gateway' and action in {'http_request', 'model.completed', 'model.failed'}
                and event.get('method', 'POST') == 'POST' else None)
        if not kind:
            continue
        tid, mid = event.get('trace_id'), event.get('message_id')
        identity = aliases.get(mid) or tid or mid or f'unlinked-{index}'
        group = groups.setdefault(identity, {'id': identity, 'trace_ids': [], 'phases': []})
        if tid and tid not in group['trace_ids']:
            group['trace_ids'].append(tid)
        end = instant(event.get('timestamp'))
        duration = event.get('duration_ms')
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not 0 <= duration <= 86400000:
            duration = None
        start = end - timedelta(milliseconds=duration) if end and duration is not None else end
        group['phases'].append({
            'id': f'{tid or identity}:{event.get("span_id") or index}:{action}',
            'kind': kind, 'module': module, 'action': action, 'trace_id': tid,
            'span_id': event.get('span_id'), 'message_id': mid,
            'parent_span_id': event.get('parent_span_id'), 'stage': event.get('stage'),
            'started_at': start.isoformat() if start else None,
            'ended_at': end.isoformat() if end else None,
            'duration_ms': duration, 'path': event.get('path'),
            'tool': event.get('tool'), 'logical_model': event.get('logical_model'),
            'status_code': event.get('status_code'), 'error_code': event.get('error_code'),
        })
    turns = []
    for group in groups.values():
        phases = group['phases']
        # HTTP timing covers streaming until completion. Callback timing on that
        # same span is additional telemetry, not another model invocation.
        http_spans = {p['span_id'] for p in phases if p['kind'] == 'model' and p['action'] == 'http_request' and p['span_id']}
        phases = [p for p in phases if not (p['kind'] == 'model' and p['action'] != 'http_request' and p['span_id'] in http_spans)]
        phases.sort(key=lambda p: (p['started_at'] or '', p['id']))
        scopes = [p for p in phases if p['kind'] == 'runtime_scope']
        for model in (p for p in phases if p['kind'] == 'model'):
            model['children'] = [p for p in phases if p['kind'] == 'model_phase' and p['parent_span_id'] == model['span_id']]
        group['runtime'] = scopes[-1] if scopes else None
        group['requests'] = [p for p in phases if p['kind'] == 'request']
        starts = [instant(p['started_at']) for p in phases if p['started_at']]
        ends = [instant(p['ended_at']) for p in phases if p['ended_at']]
        group.update(phases=[p for p in phases if p['kind'] in {'model','tool'}], started_at=min(starts).isoformat() if starts else None,
                     ended_at=max(ends).isoformat() if ends else None,
                     observed_duration_ms=(max(ends)-min(starts)).total_seconds()*1000 if starts and ends else None,
                     runtime_observed=bool(scopes),
                     model_calls=sum(p['kind'] == 'model' for p in phases))
        turns.append(group)
    turns.sort(key=lambda t: t['started_at'] or '')
    return {'items': turns[-limit:], 'truncated': len(turns) > limit}
