#!/usr/bin/env python3
"""Verify immutable ASTRA Operations v3 Library ZIP. No network or app mutations."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

EXPECTED_SHA256 = '98477755d6920d0f34e3f9abe8428c5c59c657508f23f8f611db1bc298930003'
EXPECTED_TEST_COUNT = 46

def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: verify_v3.py <checkpoint_zip>')
    archive = Path(sys.argv[1]).resolve(strict=True)
    observed = hashlib.sha256(archive.read_bytes()).hexdigest()
    if observed != EXPECTED_SHA256:
        raise SystemExit('REFUSED: immutable checkpoint SHA256 mismatch')
    with tempfile.TemporaryDirectory(prefix='astra-ops-verify-') as temp:
        base = Path(temp)
        with zipfile.ZipFile(archive) as z:
            for entry in z.infolist():
                path = Path(entry.filename)
                if (path.is_absolute() or '..' in path.parts or
                        not entry.filename.startswith('astra-operations/') or entry.is_dir()):
                    raise SystemExit('REFUSED: unsafe archive path')
            z.extractall(base)
        workdir = base / 'astra-operations'
        manifest = json.loads((workdir/'SOURCE_DIGESTS_v3.json').read_text())
        for name, digest in manifest['files'].items():
            if not name or '/' in name or '\\' in name or name.startswith('.'):
                raise SystemExit('REFUSED: invalid source file path')
            actual = hashlib.sha256((workdir/name).read_bytes()).hexdigest()
            if actual != digest:
                raise SystemExit('REFUSED: source digest mismatch: '+name)
        outcome = subprocess.run(
            [sys.executable,'-m','unittest','discover','-s','.','-p','test_*.py','-q'],
            cwd=workdir,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,check=False,timeout=60)
        print(outcome.stdout)
        if outcome.returncode != 0 or f'Ran {EXPECTED_TEST_COUNT} tests' not in outcome.stdout:
            raise SystemExit('REFUSED: tests unsuccessful or count changed')
    print('VERIFIED immutable ASTRA Operations v3 source and 46 tests; hosting/auth STILL GATED')

if __name__ == '__main__':
    main()
