import argparse
import json
from .loader import render
from .seed import apply_seed

p = argparse.ArgumentParser()
commands = p.add_subparsers(dest='command',required=True)
r = commands.add_parser('render')
r.add_argument('module'); r.add_argument('--profile',default='default')
r.add_argument('--config-root',default='config'); r.add_argument('--output',required=True); r.add_argument('--override')
s = commands.add_parser('seed-import',help='explicit model/template seed import; default is offline dry-run')
s.add_argument('seed',help='JSON path relative to config/catalog_service/seeds')
s.add_argument('--config-root',default='config'); s.add_argument('--catalog-url')
s.add_argument('--env-file',help='dotenv file read as data when --apply is used; process environment wins')
s.add_argument('--token-env',default='ADMIN_TOKEN'); s.add_argument('--revision',type=int)
s.add_argument('--replace',action='store_true',help='explicitly allow existing model replacement')
mode=s.add_mutually_exclusive_group(); mode.add_argument('--apply',action='store_true'); mode.add_argument('--dry-run',action='store_true')
a=p.parse_args()
try:
    if a.command=='render': render(a.config_root,a.module,a.output,a.profile,a.override)
    else: print(json.dumps(apply_seed(a.config_root,a.seed,apply=a.apply,catalog_url=a.catalog_url,token_env=a.token_env,revision=a.revision,replace=a.replace,env_file=a.env_file),indent=2))
except (ValueError,OSError) as error: p.exit(1,str(error)+'\n')
