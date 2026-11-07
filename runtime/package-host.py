"""Bundle public Ubuntu QEMU/e2fs executables and their native shared objects."""
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

destination = Path(sys.argv[1]).resolve()
host = destination / 'host'
for folder in ['bin', 'lib', 'modules', 'firmware']:
    (host / folder).mkdir(parents=True, exist_ok=True)
copied = {}

def copy_file(source, target):
    source = Path(source).resolve(strict=True)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise RuntimeError(f'Conflicting library basename: {target.name}')
    shutil.copy2(source, target)
    copied[str(target.relative_to(destination))] = {'source': str(source), 'sha256': digest}

def collect_libraries(executable):
    result = subprocess.run(['ldd', str(executable)], check=True, text=True, capture_output=True).stdout
    if 'not found' in result:
        raise RuntimeError(result)
    for item in re.findall(r'(?:=>\s+|^\s*)(/[^\s]+)', result, re.M):
        source = Path(item)
        copy_file(source, host / 'lib' / source.name)

for name in ['qemu-system-x86_64', 'qemu-img', 'mke2fs', 'debugfs']:
    source = Path(shutil.which(name) or '')
    if not source.is_file():
        raise RuntimeError(f'Missing required executable: {name}')
    copy_file(source, host / 'bin' / name)
    collect_libraries(source)

# Only modules owned by the QEMU packages selected for this runtime.
listing = subprocess.run(['dpkg-query', '-L', 'qemu-system-common', 'qemu-system-x86'],
                         check=True, text=True, capture_output=True).stdout
for name in sorted(set(listing.splitlines())):
    source = Path(name)
    if '/qemu/' in name and source.is_file() and source.suffix == '.so':
        copy_file(source, host / 'modules' / source.name)
        collect_libraries(source)
shutil.copytree('/usr/share/qemu', host / 'firmware', dirs_exist_ok=True, symlinks=False)
copy_file('/usr/share/seabios/bios-256k.bin', host / 'firmware' / 'bios-256k.bin')
copy_file('/etc/mke2fs.conf', host / 'mke2fs.conf')
if not (host / 'lib' / 'ld-linux-x86-64.so.2').is_file():
    raise RuntimeError('Native ELF interpreter not included')
(destination / 'provenance' / 'host-native-files.json').write_text(json.dumps(copied, indent=2) + '\n')
