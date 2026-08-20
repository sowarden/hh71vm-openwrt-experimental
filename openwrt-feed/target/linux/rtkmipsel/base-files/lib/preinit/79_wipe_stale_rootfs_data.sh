#!/bin/sh
#
# A first boot after vendor fwupg installation can find rootfs_data filled with
# leftover stock rootfs bytes because fwupg writes only kernel and rootfs. JFFS2
# rejects that content and mount_root falls back to tmpfs.
#
# Before mount_root, accept JFFS2 magic 0x1985 (85 19 in little-endian form), erased
# flash (FF FF), or an unavailable read. Any other prefix is stale content and the
# partition is erased.
#
# CRITICAL: the hook is not registered in initramfs mode. RAM boot must not modify
# flash, and mount_root is not used there.

wipe_stale_rootfs_data() {
	local index magic

	index=$(find_mtd_index rootfs_data)
	[ -n "$index" ] || return 0
	[ -c "/dev/mtd$index" ] || return 0

	magic=$(dd if="/dev/mtd$index" bs=2 count=1 2>/dev/null | \
		hexdump -v -n 2 -e '2/1 "%02x"')

	case "$magic" in
	8519|ffff|"")
		return 0
		;;
	esac

	echo "rootfs_data: stale content (0x$magic), erasing partition"
	mtd erase rootfs_data
}

[ "$INITRAMFS" = "1" ] || boot_hook_add preinit_main wipe_stale_rootfs_data
