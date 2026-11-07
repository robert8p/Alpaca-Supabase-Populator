# Portable native PostgreSQL 17 runtime

This public builder creates an Ubuntu 24.04 amd64 guest containing PostgreSQL 17 and Python psycopg, plus a self-contained native QEMU/e2fs userspace. It includes no application data, application SQL, credentials or external database endpoint. Build-time access is limited to normal public dependency repositories and the GitHub artifact service. Guest execution has no network device.

The workflow runs only on a push to `codex/native-postgres-runtime-20261107` that changes the workflow or `runtime/`. It uses a standard `ubuntu-24.04` runner, read-only repository permissions, no stored checkout credentials, a 40-minute job limit and one-day artifact retention. It has no schedule or manual-dispatch trigger. PostgreSQL packages come from the official PGDG repository, using its published signing-key fingerprint and APT signature validation.

## Local launch

Use an amd64 Linux host with Python 3.11 or newer, memory for the guest plus host overhead, and at least 6 GiB free disk space plus payload/output requirements. Guest memory defaults to 4 GiB (`--memory-mib` allows 1,024 to 8,192 MiB); the smoke uses 2 GiB. No host sudo, UID change, kernel module, KVM, container runtime or privileged mount is required. Host and guest have their own kernels and real user accounts. PostgreSQL keeps its normal root-user prohibition; payloads run as the guest's actual `pgtrial` UID 1000. Never patch privilege checks or identity functions.

After downloading the two artifact files, verify and extract them:

```bash
sha256sum -c native-postgres17-amd64.tar.xz.sha256
tar -xJf native-postgres17-amd64.tar.xz
python3 native-postgres17-amd64/launch.py \
  --input native-postgres17-amd64/smoke \
  --output native-smoke-result --timeout 600 --output-mib 512 --memory-mib 2048
```

The host smoke launch must complete and `native-smoke-result/results/work/smoke.json` must say `passed`. The packaged CI smoke is evidence from its build environment only; it does not replace the first local smoke run.

For a local payload, create a directory with `run.sh` and its files, then pass it as `--input`. This directory is placed on a read-only input disk, is never uploaded and is accessible inside the guest at `/input`. Its SHA256 manifest is checked before execution. `/output/work` is the guest user's writable directory; `OUTPUT_DIR`, `INPUT_DIR` and `PG_BINDIR` are set. The PATH contains PostgreSQL 17 binaries. Python psycopg is installed, and optional `/input/deps` is on PYTHONPATH. The payload starts and stops its own PostgreSQL cluster and must configure `listen_addresses=''` and a private Unix socket, as the generic smoke does. No application-specific code is present in this public runtime.

Output contains `launch.json`, serial log, input index, raw input/output disks and extracted `/output` files. Success requires a zero QEMU exit, successful extraction and the guest's recorded zero payload exit. A finite timeout (maximum 1,800 seconds) kills QEMU and records failure. The root image uses an ephemeral snapshot; output is a separate writable sparse disk, default 4 GiB (`--output-mib` allows 512 to 16,384 MiB). Reserve enough host space for populated database files, clones and extracted copies. No host directories, network devices, sockets, SSH or credentials are shared into the guest.

## Provenance and limitations

`SHA256SUMS` covers every delivered file except itself. `provenance/` records exact host/guest package versions, signed guest InRelease metadata, source URLs, PGDG key fingerprint, kernel version, copied native file hashes, public builder source/commit and synthetic smoke results. The delivery archive also has a separate SHA256. Upload fails closed if the compressed archive exceeds 450 MiB. Package versions are resolved from live official repositories at build time; this is a traceable bundle, not a claim of bit-for-bit reproducible builds. No application qualification is implied by its synthetic smoke test.

The bundle targets amd64 Linux and includes its dynamic ELF loader/shared libraries. Paths must contain only letters, digits, slash, dot, dash and underscore. Payload symlinks and special files are rejected. The launcher uses software emulation (TCG), not KVM. Do not add `-netdev`, networking devices, host filesystem sharing or a host service connection to this launch.

Primary dependency references:

- https://www.postgresql.org/download/linux/ubuntu/
- https://www.qemu.org/docs/master/system/linuxboot.html
- https://www.qemu.org/docs/master/system/invocation.html
- https://github.com/actions/upload-artifact/tree/v4.6.2
- https://github.com/actions/checkout/tree/11d5960a326750d5838078e36cf38b85af677262
