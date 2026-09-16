import copy
import pytest
from fastapi import HTTPException
from test.catalog_service.unit.test_catalog_management import store, SKILL


def test_resource_archive_restore_and_delete_preserves_referenced_history(store):
    store.upload_skill('demo', 'SKILL.md', SKILL)
    with pytest.raises(HTTPException, match='归档'):
        store.resource_lifecycle('demo','delete')
    store.resource_lifecycle('demo','archive')
    assert store.read()[1]['resources']['demo']['archived']
    store.resource_lifecycle('demo','restore')
    store.publish_resource('demo',copy.deepcopy(store.read()[1]['resources']['demo']['draft']))
    cfg=copy.deepcopy(store.read()[1]['agents']['agent-code']['draft'])
    cfg['bindings'].append({'id':'demo','version':1})
    store.save_agent('agent-code',cfg)
    store.resource_lifecycle('demo','archive')
    with pytest.raises(HTTPException,match='agent-code'):
        store.resource_lifecycle('demo','delete')
    assert 'demo' in store.read()[1]['resources']
    with store.edit() as data:
        data['agents']['agent-code']['versions'].append({'version':2,'config':copy.deepcopy(cfg)})
        data['agents']['agent-code']['draft']['bindings'] = []
    with pytest.raises(HTTPException,match='历史版本'):
        store.resource_lifecycle('demo','delete')
    store.upload_skill('unused','SKILL.md',SKILL)
    store.resource_lifecycle('unused','archive')
    store.resource_lifecycle('unused','delete')
    assert 'unused' not in store.read()[1]['resources']
    assert 'demo' in store.read()[1]['resources']


def test_resource_delete_respects_catalog_revision(store):
    store.upload_skill('unused','SKILL.md',SKILL)
    revision=store.read()[0]
    store.resource_lifecycle('unused','archive')
    with pytest.raises(HTTPException):
        store.resource_lifecycle('unused','delete',revision)
    assert 'unused' in store.read()[1]['resources']
