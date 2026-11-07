#!/bin/bash
# Run only on a fresh Ubuntu 24.04 GitHub-hosted standard public runner.
set -Eeuo pipefail
source_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
task_root="${RUNNER_TEMP:?RUNNER_TEMP is required}/native-pg-runtime-build"
delivery="${RUNNER_TEMP}/native-pg-runtime-delivery"
test "${GITHUB_ACTIONS:-}" = true
test "${GITHUB_EVENT_NAME:-}" = push
test "${GITHUB_REF:-}" = refs/heads/codex/native-postgres-runtime-20261107
test "$(dpkg --print-architecture)" = amd64
test "$(. /etc/os-release; printf '%s' "$VERSION_ID")" = 24.04
test ! -e "$task_root"
test ! -e "$delivery"
mkdir -p "$task_root" "$delivery"
guest="$task_root/rootfs"
bundle="$task_root/native-postgres17-amd64"
mkdir -p "$bundle/provenance" "$bundle/guest" "$bundle/smoke"
cleanup() {
  mountpoint -q "$guest/proc" && sudo umount "$guest/proc" || true
  mountpoint -q "$guest/sys" && sudo umount "$guest/sys" || true
}
trap cleanup EXIT

# Public packages only. No full-system upgrade or repository credentials.
sudo apt-get update
sudo apt-get install -y --no-install-recommends debootstrap qemu-system-x86 qemu-utils \
  seabios curl ca-certificates gnupg ubuntu-keyring xz-utils e2fsprogs python3
dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n' > "$bundle/provenance/host-packages.tsv"
sudo debootstrap --arch=amd64 --variant=minbase --components=main,universe \
  --keyring=/usr/share/keyrings/ubuntu-archive-keyring.gpg \
  noble "$guest" https://archive.ubuntu.com/ubuntu
sudo install -d "$guest/usr/share/keyrings" "$guest/usr/local/sbin" "$guest/etc/apt/sources.list.d" "$guest/etc/ssl/certs"
sudo cp /usr/share/keyrings/ubuntu-archive-keyring.gpg "$guest/usr/share/keyrings/"
# minbase may not yet contain ca-certificates; preserve HTTPS verification for
# its first apt update using the runner's public distro CA trust bundle.
sudo cp /etc/ssl/certs/ca-certificates.crt "$guest/etc/ssl/certs/ca-certificates.crt"
curl --proto '=https' --tlsv1.2 --fail --show-error --location --max-time 60 \
  https://www.postgresql.org/media/keys/ACCC4CF8.asc -o "$task_root/pgdg.asc"
fingerprint="$(gpg --batch --show-keys --with-colons "$task_root/pgdg.asc" | awk -F: '$1=="fpr" {print $10; exit}')"
test "$fingerprint" = B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8
printf '%s\n' "$fingerprint" > "$bundle/provenance/pgdg-key-fingerprint.txt"
sudo cp "$task_root/pgdg.asc" "$guest/usr/share/keyrings/pgdg.asc"
sudo tee "$guest/etc/apt/sources.list" >/dev/null <<'SOURCES'
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu noble main universe
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://archive.ubuntu.com/ubuntu noble-updates main universe
deb [signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg] https://security.ubuntu.com/ubuntu noble-security main universe
SOURCES
sudo tee "$guest/etc/apt/sources.list.d/pgdg.list" >/dev/null <<'SOURCES'
deb [arch=amd64 signed-by=/usr/share/keyrings/pgdg.asc] https://apt.postgresql.org/pub/repos/apt noble-pgdg main
SOURCES
sudo tee "$guest/usr/sbin/policy-rc.d" >/dev/null <<'POLICY'
#!/bin/sh
exit 101
POLICY
sudo chmod 755 "$guest/usr/sbin/policy-rc.d"
sudo cp "$source_dir/guest-init.sh" "$guest/usr/local/sbin/native-runtime-init"
sudo chmod 755 "$guest/usr/local/sbin/native-runtime-init"
sudo mount -t proc proc "$guest/proc"
sudo mount -t sysfs sysfs "$guest/sys"
sudo tee "$guest/tmp/provision-runtime.sh" >/dev/null <<'PROVISION'
#!/bin/bash
set -Eeuo pipefail
apt-get update
apt-get install -y --no-install-recommends ca-certificates postgresql-common
printf '\ncreate_main_cluster = false\n' >> /etc/postgresql-common/createcluster.conf
apt-get install -y --no-install-recommends postgresql-17 postgresql-client-17 python3 python3-psycopg \
  linux-image-virtual initramfs-tools busybox-static util-linux passwd
printf '%s\n' virtio virtio_pci virtio_blk ext4 >> /etc/initramfs-tools/modules
update-initramfs -u -k all
useradd --uid 1000 --create-home --shell /bin/bash pgtrial
passwd --lock pgtrial
install -d -m 755 /input /output
dpkg-query -W -f='${Package}\t${Version}\t${Architecture}\n' > /tmp/guest-packages.tsv
apt-cache policy postgresql-17 python3-psycopg linux-image-virtual > /tmp/guest-package-policy.txt
/usr/lib/postgresql/17/bin/postgres --version > /tmp/postgres-version.txt
python3 -c 'import psycopg; print(psycopg.__version__)' > /tmp/psycopg-version.txt
find /var/cache/apt/archives -type f -name '*.deb' -exec sha256sum {} + > /tmp/downloaded-debs.sha256
apt-get clean
rm -f /etc/machine-id /var/lib/dbus/machine-id
truncate -s 0 /etc/machine-id
printf '%s\n' native-runtime > /etc/hostname
printf '%s\n' '127.0.0.1 localhost native-runtime' > /etc/hosts
rm -f /etc/resolv.conf
touch /etc/resolv.conf
PROVISION
sudo chroot "$guest" /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin \
  HOME=/root LANG=C.UTF-8 LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive \
  /bin/bash /tmp/provision-runtime.sh
for name in guest-packages.tsv guest-package-policy.txt postgres-version.txt psycopg-version.txt downloaded-debs.sha256; do
  sudo cp "$guest/tmp/$name" "$bundle/provenance/$name"
done
sudo cp "$guest/etc/apt/sources.list" "$bundle/provenance/guest-ubuntu-sources.list"
sudo cp "$guest/etc/apt/sources.list.d/pgdg.list" "$bundle/provenance/guest-pgdg-sources.list"
sudo cp "$guest/usr/share/keyrings/pgdg.asc" "$bundle/provenance/pgdg.asc"
sudo cp "$guest/usr/share/keyrings/ubuntu-archive-keyring.gpg" "$bundle/provenance/ubuntu-archive-keyring.gpg"
sudo mkdir -p "$bundle/provenance/guest-inrelease"
sudo find "$guest/var/lib/apt/lists" -maxdepth 1 -type f -name '*InRelease' -exec cp {} "$bundle/provenance/guest-inrelease/" \;
kernel="$(find "$guest/boot" -maxdepth 1 -type f -name 'vmlinuz-*' | sort -V | tail -n 1)"
test -n "$kernel"
kernel_version="${kernel##*/vmlinuz-}"
sudo cp "$kernel" "$bundle/guest/vmlinuz"
sudo cp "$guest/boot/initrd.img-$kernel_version" "$bundle/guest/initrd.img"
printf '%s\n' "$kernel_version" > "$bundle/provenance/kernel-version.txt"
cleanup
if mountpoint -q "$guest/proc" || mountpoint -q "$guest/sys"; then
  printf '%s\n' 'Guest build mounts remain active; refusing to create the root image.' >&2
  exit 1
fi
sudo rm -rf "$guest/var/lib/apt/lists/"* "$guest/var/log/"* "$guest/tmp/"* "$guest/boot/"*
truncate -s 2G "$bundle/guest/rootfs.ext4"
sudo mkfs.ext4 -q -F -L NATIVERUNTIME -m 0 -d "$guest" "$bundle/guest/rootfs.ext4"
sudo chown -R "$(id -u):$(id -g)" "$bundle"
python3 "$source_dir/package-host.py" "$bundle"
cp "$source_dir/launch.py" "$bundle/launch.py"
cp "$source_dir/smoke-run.sh" "$bundle/smoke/run.sh"
cp "$source_dir/smoke.py" "$bundle/smoke/smoke.py"
cp "$source_dir/README.md" "$bundle/README.md"
cp "$source_dir"/*.sh "$source_dir"/*.py "$bundle/provenance/"
python3 - "$bundle" <<'INDEX'
import datetime,hashlib,json,os,sys
from pathlib import Path
root=Path(sys.argv[1])
record={'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'builder_commit':os.environ['GITHUB_SHA'],'run_url':f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
        'host':'Ubuntu 24.04 amd64','guest':'Ubuntu 24.04 amd64','postgres_major':17,
        'guest_network':'none','acceleration':'tcg','public_packages_only':True,
        'ubuntu_mirror':'https://archive.ubuntu.com/ubuntu','pgdg_repository':'https://apt.postgresql.org/pub/repos/apt',
        'reproducibility':'Exact installed versions, signed metadata and packaged bytes are recorded; live repository resolution is not a reproducible-build claim.'}
(root/'provenance/build.json').write_text(json.dumps(record,indent=2)+'\n')
with (root/'SHA256SUMS').open('w') as index:
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name!='SHA256SUMS':
            with p.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            index.write(f'{digest}  {p.relative_to(root)}\n')
INDEX
# This verifies the packaged launcher and real guest UID, PostgreSQL and psycopg.
if ! python3 "$bundle/launch.py" --input "$bundle/smoke" --output "$task_root/smoke-result" --timeout 600 --output-mib 512 --memory-mib 2048; then
  # This job's input is the public synthetic smoke only. Preserve boot evidence
  # without uploading any root filesystem, payload disk or private workload.
  for name in launch.json console.log extract.log; do
    if test -f "$task_root/smoke-result/$name"; then
      printf '\n--- Generic runtime smoke failure: %s ---\n' "$name"
      cat "$task_root/smoke-result/$name"
    fi
  done
  exit 1
fi
cp "$task_root/smoke-result/results/work/smoke.json" "$bundle/provenance/smoke-result.json"
cp "$task_root/smoke-result/launch.json" "$bundle/provenance/smoke-launch.json"
cp "$task_root/smoke-result/console.log" "$bundle/provenance/smoke-console.log"
python3 - "$bundle" <<'INDEX'
import hashlib,sys
from pathlib import Path
root=Path(sys.argv[1])
with (root/'SHA256SUMS').open('w') as index:
    for p in sorted(root.rglob('*')):
        if p.is_file() and p.name!='SHA256SUMS':
            with p.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
            index.write(f'{digest}  {p.relative_to(root)}\n')
INDEX
XZ_OPT='-T2 -3' tar -C "$task_root" -cJf "$delivery/native-postgres17-amd64.tar.xz" native-postgres17-amd64
test "$(stat -c %s "$delivery/native-postgres17-amd64.tar.xz")" -le 471859200
(cd "$delivery" && sha256sum native-postgres17-amd64.tar.xz > native-postgres17-amd64.tar.xz.sha256)
