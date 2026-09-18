"""Install only the checked sqlite3 5.1.7 Windows x64 binary; no package hooks."""
import argparse
import hashlib
import tarfile
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('archive', type=Path, help='Official sqlite3-v5.1.7-napi-v6-win32-x64.tar.gz')
args = parser.parse_args()
with tarfile.open(args.archive) as tar:
    members = tar.getmembers()
    if len(members) != 1 or members[0].name != 'build/Release/node_sqlite3.node':
        raise RuntimeError('Unexpected archive contents')
    member = members[0]
    if not member.isfile() or not 0 < member.size < 10 * 1024 * 1024:
        raise RuntimeError('Invalid binary entry')
    data = tar.extractfile(member).read()
    if len(data) != member.size:
        raise RuntimeError('Incomplete archive')
expected = 'f806f89dc41dde00ca7124dc1e649bdc9b08ff2eff5c891b764f3e5aefa9548c'
if hashlib.sha256(data).hexdigest() != expected:
    raise RuntimeError('Binary hash differs from the reviewed version')
target = Path(__file__).resolve().parents[1] / 'n8n/node_modules/sqlite3/build/Release/node_sqlite3.node'
target.parent.mkdir(parents=True, exist_ok=True)
if target.exists() and target.read_bytes() != data:
    raise RuntimeError('Refusing to overwrite a different binary')
target.write_bytes(data)
print('Installed checked SQLite binary without executing package scripts.')
