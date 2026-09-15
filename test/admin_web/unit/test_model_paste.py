import json
import pytest
from fastapi import HTTPException
from admin_web.local_service.importer import Importer


def config(key='test-only-key'):
    return {'model': 'minimax/MiniMax-M3', 'provider': {'minimax': {
        'npm': '@ai-sdk/openai-compatible',
        'options': {'apiKey': key, 'baseURL': 'https://api.minimaxi.com/v1'},
        'models': {'MiniMax-M3': {'name': 'Coding', 'limit': {'context': 100000, 'output': 8192}}},
    }}}


@pytest.mark.parametrize('escaped', [False, True])
def test_jsonc_and_escaped_text_fill_models_without_saving(tmp_path, escaped):
    text = '// comment\n' + json.dumps(config())[:-1] + ',}'
    result = Importer(tmp_path).parse_text(json.dumps(text) if escaped else text)
    assert not result['errors']
    assert result['models'][0]['api_key'] == 'test-only-key'
    assert result['models'][0]['upstream_model'] == 'MiniMax-M3'
    assert result['models'][0]['context'] == 100000
    assert not list(tmp_path.iterdir())


def test_paste_does_not_read_environment_or_files(tmp_path, monkeypatch):
    monkeypatch.setenv('SECRET', 'must-not-read')
    for ref in ('{env:SECRET}', '{file:/etc/passwd}'):
        result = Importer(tmp_path).parse_text(json.dumps(config(ref)))
        assert not result['errors']
        assert result['models'][0]['api_key'] == ''
        assert result['unresolved'] == ['.provider.minimax.options.apiKey']
        assert 'must-not-read' not in json.dumps(result)


def test_unsupported_options_and_colliding_ids_do_not_silently_fill(tmp_path):
    value = config()
    value['provider']['minimax']['options']['unsupported'] = True
    result = Importer(tmp_path).parse_text(json.dumps(value))
    assert result['errors'] and not result['models']
    with pytest.raises(HTTPException): Importer(tmp_path).parse_text('not json')
    with pytest.raises(HTTPException): Importer(tmp_path).parse_text('{"provider":[]}')
    provider = config()['provider']['minimax']
    collision = {'provider': {'a/b': provider, 'a-b': provider}}
    assert Importer(tmp_path).parse_text(json.dumps(collision))['errors']
