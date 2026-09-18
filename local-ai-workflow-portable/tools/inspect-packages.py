"""Inventory locked packages without running any dependency scripts."""
import json
from pathlib import Path
from urllib.parse import urlparse

root = Path(__file__).resolve().parents[1]
packages = root / 'n8n'
lock = json.loads((packages / 'package-lock.json').read_text(encoding='utf-8-sig'))
origins, missing, hooks = {}, [], []
for path, item in lock.get('packages', {}).items():
    if not path:
        continue
    resolved = item.get('resolved', '')
    host = urlparse(resolved).hostname or '(local/unspecified)'
    origins[host] = origins.get(host, 0) + 1
    if resolved.startswith('https:') and not item.get('integrity'):
        missing.append(path)
    manifest = packages / path / 'package.json'
    if manifest.is_file():
        data = json.loads(manifest.read_text(encoding='utf-8'))
        scripts = {k:v for k,v in data.get('scripts', {}).items() if k in ('preinstall','install','postinstall')}
        if scripts:
            hooks.append({'path':path, 'name':data.get('name'), 'version':data.get('version'), 'hooks':scripts})
report = {'registry_hosts':origins, 'missing_integrity':missing, 'installed_package_hooks':hooks}
(root / 'logs').mkdir(exist_ok=True)
(root / 'logs/package-inspection.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
