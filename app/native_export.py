"""Native OpenCode layout, compiled by the same runtime compiler as Agent publish."""
import io
import json
import zipfile

from app.management import fail


def export_native(runtime, aid):
    _, catalog = runtime.store.read()
    agent = catalog['agents'].get(aid)
    if not agent:
        fail('Agent not found', 404)
    config = runtime.store.agent_config(agent) or agent['draft']
    native = runtime.compile_agent(catalog, aid, config, agent['active'] or 0, preview=True)['opencode']
    native['instructions'] = ['AGENTS.md']
    native['skills'] = {'paths':['./skills']}
    native['plugin'] = []
    # Export is a reference to the existing gateway, not a provider-key export.
    native['provider']['cloud-model-gateway']['options']['baseURL'] = runtime.backend.config.model_gateway.base_url
    out = io.BytesIO()
    total = 0
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for binding in config['bindings']:
            resource, version = runtime.store.resource_version(catalog, binding['id'], binding['version'])
            if resource['kind'] not in {'skill', 'hook'}:
                continue
            directory = ('skills/' if resource['kind'] == 'skill' else 'plugins/') + resource['id']
            for path, digest in version['files'].items():
                content = runtime.store.file(digest)
                total += len(content)
                if total > 100*1024**2:
                    fail('Native export exceeds 100 MiB', 413)
                archive.writestr(directory+'/'+path, content)
            if resource['kind'] == 'hook':
                native['plugin'].append('./'+directory+'/'+version['data'].get('compiled_entry',version['data']['entry']))
        archive.writestr('opencode.json', json.dumps(native, indent=2, ensure_ascii=False))
        archive.writestr('AGENTS.md', config.get('instructions',''))
        archive.writestr('README.txt', 'This configuration depends on the original LiteLLM gateway. Set its reachable baseURL before use. Provider credentials are not included. MCP secret placeholders must be filled. Local MCP commands still require the matching sandbox dependencies. The platform system trace plugin is not exported.\n')
    return out.getvalue()
