import json
import pytest
from config.tooling.seed import apply_seed, read_env_file

@pytest.fixture
def root(tmp_path):
    path=tmp_path/'catalog_service/seeds';path.mkdir(parents=True)
    (path/'seed.json').write_text(json.dumps({'schema_version':1,'models':[{'id':'demo','provider':'openai-compatible','upstream_model':'demo','api_key':'${SEED_KEY}'}]}))
    return tmp_path

def test_default_plan_never_calls_network_or_resolves_secrets(root):
    result=apply_seed(root,'seed.json',request=lambda *args:pytest.fail('dry run called network'))
    assert result['mode']=='dry-run' and result['model_ids']==['demo'] and not result['published']
    assert 'api_key' not in json.dumps(result)

def test_explicit_apply_resolves_only_payload_and_requires_revision(root):
    calls=[]
    result=apply_seed(root,'seed.json',apply=True,catalog_url='http://catalog:8101',revision=4,
                      environ={'ADMIN_TOKEN':'auth','SEED_KEY':'sensitive'},request=lambda path,payload:calls.append((path,payload)))
    assert calls==[('/cloud/admin/models/import',{'models':[{'id':'demo','provider':'openai-compatible','upstream_model':'demo','api_key':'sensitive'}],'replace':False,'revision':4})]
    assert 'sensitive' not in json.dumps(result)
    assert result['completed']==['models.import']

@pytest.mark.parametrize('revision,environ',[(None,{'ADMIN_TOKEN':'auth','SEED_KEY':'x'}),(1,{'ADMIN_TOKEN':'auth'})])
def test_missing_preconditions_never_write(root,revision,environ):
    with pytest.raises(ValueError): apply_seed(root,'seed.json',apply=True,catalog_url='http://catalog:8101',revision=revision,environ=environ,request=lambda *args:pytest.fail('unexpected write'))

def test_path_escape_and_plaintext_secrets_rejected(root):
    with pytest.raises(ValueError): apply_seed(root,'../../outside.json')
    path=root/'catalog_service/seeds/seed.json'
    path.write_text(path.read_text().replace('${SEED_KEY}','plaintext'))
    with pytest.raises(ValueError,match='environment references'): apply_seed(root,'seed.json')

def test_template_restore_uses_existing_contract(root):
    (root/'catalog_service/seeds/template.json').write_text(json.dumps({'schema_version':1,'templates':[{'template_id':'base','agent_id':'new-agent','models':{'old':'demo'},'resources':{}}]}))
    calls=[]
    result=apply_seed(root,'template.json',apply=True,catalog_url='http://catalog:8101',environ={'ADMIN_TOKEN':'auth'},request=lambda path,payload:calls.append((path,payload)))
    assert calls[0][0]=='/cloud/admin/agent-templates/base/restore'
    assert calls[0][1]['agent_id']=='new-agent' and not result['published']

def test_env_file_is_parsed_as_literal_data(tmp_path):
    marker=tmp_path/'must-not-exist'
    env_file=tmp_path/'.env'
    env_file.write_text(
        '# comment\nexport ADMIN_TOKEN="admin token"\n'
        'SEED_MODEL_BASE_URL=https://provider.example/v1#fragment\n'
        "SEED_MODEL_NAME='model name'\n"
        f'SEED_MODEL_API_KEY=$(touch {marker}) # literal value\n'
    )
    values=read_env_file(env_file)
    assert values=={
        'ADMIN_TOKEN':'admin token',
        'SEED_MODEL_BASE_URL':'https://provider.example/v1#fragment',
        'SEED_MODEL_NAME':'model name',
        'SEED_MODEL_API_KEY':f'$(touch {marker})',
    }
    assert not marker.exists()

def test_apply_loads_env_file_and_process_environment_wins(root,tmp_path):
    seed=root/'catalog_service/seeds/seed.json'
    seed.write_text(json.dumps({'schema_version':1,'models':[{
        'id':'demo','provider':'openai-compatible','upstream_model':'${SEED_MODEL_NAME}',
        'base_url':'${SEED_MODEL_BASE_URL}','api_key':'${SEED_MODEL_API_KEY}'
    }]}))
    env_file=tmp_path/'.env'
    env_file.write_text(
        'ADMIN_TOKEN=file-auth\nSEED_MODEL_NAME=file-model\n'
        'SEED_MODEL_BASE_URL=https://provider.example/v1\nSEED_MODEL_API_KEY=file-secret\n'
    )
    calls=[]
    result=apply_seed(root,'seed.json',apply=True,catalog_url='http://catalog:8101',revision=7,
                      env_file=env_file,environ={'ADMIN_TOKEN':'process-auth','SEED_MODEL_NAME':'process-model'},
                      request=lambda path,payload:calls.append((path,payload)))
    model=calls[0][1]['models'][0]
    assert model=={'id':'demo','provider':'openai-compatible','upstream_model':'process-model',
                   'base_url':'https://provider.example/v1','api_key':'file-secret'}
    assert result['completed']==['models.import'] and 'file-secret' not in json.dumps(result)

@pytest.mark.parametrize('content', ['NO_EQUALS', 'BAD-NAME=value', 'KEY="unterminated'])
def test_invalid_env_file_fails_before_request(root,tmp_path,content):
    env_file=tmp_path/'.env';env_file.write_text(content)
    with pytest.raises(ValueError,match='env'):
        apply_seed(root,'seed.json',apply=True,catalog_url='http://catalog:8101',revision=1,
                   env_file=env_file,environ={},request=lambda *args:pytest.fail('unexpected write'))
