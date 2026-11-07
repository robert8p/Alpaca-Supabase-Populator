#!/bin/bash
# PID 1 inside a disposable, networkless guest. Never runs on the host.
set -Eeuo pipefail
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
result=1
finish() {
  result=$?
  trap - EXIT
  if mountpoint -q /output; then
    printf '%s\n' "$result" > /output/exit_code
    sync
  fi
  printf 'NATIVE_RUNTIME_EXIT=%s\n' "$result" > /dev/console
  /bin/busybox poweroff -f
}
trap finish EXIT
trap 'printf "NATIVE_RUNTIME_FAILURE line=%s\n" "$LINENO" > /dev/console' ERR
printf 'NATIVE_RUNTIME_STAGE=mounting_guest_filesystems\n' > /dev/console
mountpoint -q /proc || mount -t proc proc /proc
mountpoint -q /sys || mount -t sysfs sysfs /sys
mountpoint -q /dev || mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts /run /input /output
mountpoint -q /dev/pts || mount -t devpts devpts /dev/pts
mount -t tmpfs -o mode=755,nosuid,nodev tmpfs /run
ln -sfn /proc/self/fd /dev/fd
printf 'NATIVE_RUNTIME_STAGE=mounting_payload_disks\n' > /dev/console
mount -o ro,nosuid,nodev /dev/vdb /input
mount -o rw,nosuid,nodev /dev/vdc /output
exec > >(tee /output/guest.log /dev/console) 2>&1
printf 'NATIVE_RUNTIME_STAGE=verifying_payload\n'
test -f /input/run.sh
cd /input
sha256sum -c INPUT_SHA256SUMS > /output/input-verification.log
test "$(id -u pgtrial)" -ne 0
install -d -o pgtrial -g pgtrial -m 700 /output/work
printf '%s\n' "$(id pgtrial)" > /output/guest-user.txt
printf 'NATIVE_RUNTIME_STAGE=running_nonroot_payload\n'
# No credentials or host environment are passed through to the payload.
runuser -u pgtrial -- env -i \
  PATH=/usr/lib/postgresql/17/bin:/usr/bin:/bin \
  HOME=/home/pgtrial LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  PG_BINDIR=/usr/lib/postgresql/17/bin \
  INPUT_DIR=/input OUTPUT_DIR=/output/work \
  PYTHONPATH=/input/deps PYTHONDONTWRITEBYTECODE=1 \
  /bin/bash /input/run.sh
