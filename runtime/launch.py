"""Launch a native, networkless VM as an ordinary host process. Standard Python only."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent

def checked_path(value):
    result = Path(value).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_./-]+', str(result)):
        raise ValueError('Use paths containing only letters, digits, slash, dot, dash and underscore')
    return result

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='Payload directory containing run.sh; never uploaded')
    parser.add_argument('--output', required=True, help='New local output directory')
    parser.add_argument('--timeout', type=int, default=1800, help='Finite wall-clock seconds, maximum 1800')
    parser.add_argument('--output-mib', type=int, default=4096, help='Sparse output disk MiB, 512 to 16384')
    parser.add_argument('--memory-mib', type=int, default=4096, help='Guest memory MiB, 1024 to 8192')
    args = parser.parse_args()
    if not 30 <= args.timeout <= 1800:
        raise ValueError('Timeout must be between 30 and 1800 seconds')
    if not 512 <= args.output_mib <= 16384:
        raise ValueError('Output disk must be between 512 and 16384 MiB')
    if not 1024 <= args.memory_mib <= 8192:
        raise ValueError('Guest memory must be between 1024 and 8192 MiB')
    bundle, source, output = map(checked_path, [BUNDLE, args.input, args.output])
    if not (source / 'run.sh').is_file() or source.is_symlink():
        raise ValueError('Input must be a real directory containing run.sh')
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('Input and output directories must be separate')
    if output.exists():
        raise ValueError('Output directory must not already exist')
    # Fail before launching if the delivered runtime was altered or truncated.
    for line in (bundle / 'SHA256SUMS').read_text().splitlines():
        expected, relative = line.split('  ', 1)
        path = bundle / relative
        if path.resolve().is_relative_to(bundle) is False or sha(path) != expected:
            raise RuntimeError(f'Bundle verification failed: {relative}')
    output.mkdir(parents=True)
    stage = output / 'input-stage'
    stage.mkdir()
    for path in sorted(source.rglob('*')):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError(f'Input contains symlink or special file: {path}')
        target = stage / path.relative_to(source)
        if path.is_dir():
            target.mkdir(exist_ok=True)
        else:
            shutil.copy2(path, target)
    if (stage / 'INPUT_SHA256SUMS').exists():
        raise ValueError('INPUT_SHA256SUMS is reserved for launcher verification')
    (stage / 'INPUT_SHA256SUMS').write_text(''.join(
        f'{sha(p)}  {p.relative_to(stage)}\n' for p in sorted(stage.rglob('*')) if p.is_file()))
    environment = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C',
                   'QEMU_MODULE_DIR': str(bundle / 'host/modules'),
                   'MKE2FS_CONFIG': str(bundle / 'host/mke2fs.conf')}

    def host_command(name, *arguments):
        return [str(bundle / 'host/lib/ld-linux-x86-64.so.2'),
                '--library-path', str(bundle / 'host/lib'), str(bundle / 'host/bin' / name), *map(str, arguments)]

    for name, label, size, contents in [
        ('input.raw', 'NATIVEINPUT', max(64 << 20, 3 * sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())), stage),
        ('output.raw', 'NATIVEOUTPUT', args.output_mib << 20, None),
    ]:
        path = output / name
        with path.open('xb') as stream:
            stream.truncate(size)
        subprocess.run(host_command('mke2fs', '-q', '-F', '-t', 'ext4', '-L', label, '-m', '0',
                       *(['-d', contents] if contents else []), path), env=environment, check=True)
    command = host_command('qemu-system-x86_64', '-machine', 'pc,accel=tcg',
        '-m', str(args.memory_mib), '-smp', '2', '-display', 'none', '-serial', 'stdio', '-monitor', 'none',
        '-no-reboot', '-nic', 'none', '-vga', 'none',
        '-L', bundle / 'host/firmware', '-bios', bundle / 'host/firmware/bios-256k.bin',
        '-drive', f'file={bundle}/guest/rootfs.ext4,if=virtio,format=raw,snapshot=on',
        '-drive', f'file={output}/input.raw,if=virtio,format=raw,readonly=on',
        '-drive', f'file={output}/output.raw,if=virtio,format=raw',
        '-kernel', bundle / 'guest/vmlinuz', '-initrd', bundle / 'guest/initrd.img',
        '-append', 'root=/dev/vda rw rootwait console=ttyS0 panic=-1 init=/usr/local/sbin/native-runtime-init')
    report = {'status': 'running', 'network': 'none', 'acceleration': 'tcg',
              'host_uid': os.getuid(), 'timeout_seconds': args.timeout,
              'output_disk_mib': args.output_mib,
              'guest_memory_mib': args.memory_mib,
              'input_index_sha256': sha(stage / 'INPUT_SHA256SUMS'), 'command': command}
    (output / 'launch.json').write_text(json.dumps(report, indent=2) + '\n')
    started = time.monotonic()
    with (output / 'console.log').open('wb') as log:
        try:
            process = subprocess.run(command, env=environment, stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, timeout=args.timeout)
            report['qemu_exit_code'] = process.returncode
        except subprocess.TimeoutExpired:
            report['status'] = 'timed_out'
            report['qemu_exit_code'] = None
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    results = output / 'results'
    results.mkdir()
    with (output / 'extract.log').open('wb') as log:
        extraction = subprocess.run(host_command('debugfs', '-R', f'rdump / {results}', output / 'output.raw'),
            env=environment, stdout=log, stderr=subprocess.STDOUT, timeout=60)
    report['extract_exit_code'] = extraction.returncode
    exit_file = results / 'exit_code'
    report['guest_exit_code'] = int(exit_file.read_text().strip()) if exit_file.is_file() else None
    passed = report['qemu_exit_code'] == 0 and extraction.returncode == 0 and report['guest_exit_code'] == 0
    if report['status'] != 'timed_out':
        report['status'] = 'completed' if passed else 'failed'
    (output / 'launch.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ['status', 'elapsed_seconds', 'qemu_exit_code', 'guest_exit_code']}))
    return 0 if passed else 1

if __name__ == '__main__':
    sys.exit(main())
