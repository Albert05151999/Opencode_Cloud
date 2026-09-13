"""Service decomposition gates: no monolith imports or sibling implementation dependencies."""
import ast
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULES = ('api_gateway', 'catalog_service', 'sandbox_manager', 'file_service', 'model_gateway', 'operations', 'observability', 'agent_runtime')

@pytest.mark.parametrize('module', MODULES)
def test_no_cross_service_business_imports(module):
    violations = []
    for source in (ROOT / module).rglob('*.py'):
        tree = ast.parse(source.read_text(), filename=str(source))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import): names = [alias.name for alias in node.names]
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module: names = [node.module]
            for name in names:
                top = name.split('.')[0]
                if top == 'app' or (top in MODULES and top != module) or top in ('web', 'local_web', 'admin_web'):
                    violations.append(f'{source.relative_to(ROOT)}:{node.lineno}: {name}')
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module' and node.args and isinstance(node.args[0], ast.Constant):
                name = node.args[0].value
                if isinstance(name, str) and (name == 'app' or name.startswith('app.')):
                    violations.append(f'{source.relative_to(ROOT)}:{node.lineno}: dynamic {name}')
    assert not violations, '\n'.join(violations)

@pytest.mark.parametrize('module', MODULES)
def test_manifest_build_inputs_are_explicit(module):
    path = ROOT / module / 'module.yaml'
    assert path.exists(), f'{module} missing module.yaml'
    value = json.loads(path.read_text())
    assert value['module_id'] == module
    assert value['version'] and value['entrypoint']
    build = value['build']
    assert build['sources']
    for source in build['sources']:
        assert Path(source).parts[0] in (module, 'contracts')
        assert (ROOT / source).exists()
    if module != 'agent_runtime':
        assert (ROOT / build['requirements']).is_file()
        assert build['shared_libs']['version'] == (ROOT / 'shared_libs/VERSION').read_text().strip()
    recipe = ROOT / 'build_image/modules' / module / 'Dockerfile'
    assert recipe.exists() and 'COPY . ' not in recipe.read_text()

@pytest.mark.parametrize('module', MODULES)
def test_no_runtime_root_docs_dependency(module):
    for source in (ROOT / module).rglob('*.py'):
        text = source.read_text()
        assert 'docs/upstream' not in text, str(source)
        assert 'Path("docs")' not in text and "Path('docs')" not in text, str(source)
        assert '/ "docs" /' not in text and "/ 'docs' /" not in text, str(source)


def test_shared_libraries_do_not_depend_on_business_modules():
    for source in (ROOT / 'shared_libs').rglob('*.py'):
        for node in ast.walk(ast.parse(source.read_text())):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0: names.append(node.module)
            assert not any(name.split('.')[0] in (*MODULES, 'app', 'admin_web') for name in names), str(source)
