from fastapi.testclient import TestClient
from catalog_service.main import create_app


def test_api_mapping_preview_and_release_use_same_alias_and_accounts(tmp_path, monkeypatch):
    monkeypatch.setenv('SERVICE_TOKEN', 'mapping-token')
    app = create_app(tmp_path)
    model = {'id': 'coding', 'provider': 'openai-compatible', 'upstream_model': 'MiniMax-M3',
             'base_url': 'https://api.minimaxi.com/v1',
             'deployments': [{'id': 'a', 'api_key': 'secret-a'}, {'id': 'b', 'api_key': 'secret-b'}]}
    with TestClient(app, headers={'Authorization': 'Bearer mapping-token'}) as client:
        preview = client.post('/cloud/admin/models/config-preview', json={'model': model})
        assert preview.status_code == 200, preview.text
        assert 'secret-a' not in preview.text and 'secret-b' not in preview.text
        assert preview.json()['agent']['model'] == 'cloud-model-gateway/coding'
        assert len(preview.json()['gateway']) == 2
        revision = client.get('/cloud/admin/catalog').json()['revision']
        saved = client.put('/cloud/admin/models/coding', json={'model': model, 'revision': revision})
        assert saved.status_code == 200, saved.text
        revision = client.get('/cloud/admin/catalog').json()['revision']
        release = client.post('/internal/v1/releases/prepare', json={'kind': 'models.apply', 'revision': revision})
        assert release.status_code == 200, release.text
        entries = release.json()['configuration']['model_list']
        assert [e['model_info'] for e in entries] == [e['model_info'] for e in preview.json()['gateway']]
        assert [e['litellm_params']['api_key'] for e in entries] == ['secret-a', 'secret-b']
        # An incomplete draft is editable/previewable but cannot become a release.
        model['deployments'][1]['api_key'] = ''
        revision = client.get('/cloud/admin/catalog').json()['revision']
        assert client.put('/cloud/admin/models/coding', json={'model': model, 'revision': revision}).status_code == 200
        revision = client.get('/cloud/admin/catalog').json()['revision']
        blocked = client.post('/internal/v1/releases/prepare', json={'kind': 'models.apply', 'revision': revision})
        assert blocked.status_code == 400 and 'real API key' in blocked.text
