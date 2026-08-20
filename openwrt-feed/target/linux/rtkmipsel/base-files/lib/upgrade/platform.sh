#
# sysupgrade implementation for Realtek RTL8197F / HH71VM development builds.
#
# A *-sysupgrade.bin contains a cr6c-wrapped kernel padded to KERNEL_PART_SIZE,
# followed by the stamped squashfs root. Kernel and rootfs are written separately;
# boot and hwsetting are never targeted by this path.
#
# Public releases currently provide no prebuilt sysupgrade image and no supported
# flash-install procedure. This code remains in the source snapshot for completeness.

. /lib/functions/system.sh
. /lib/rtkmipsel.sh

KERNEL_PART_SIZE=2949120

get_magic_str() {
	(get_image "$@" | dd bs=4 count=1) 2>/dev/null
}

platform_check_image() {
	local signature size

	[ "$#" -gt 1 ] && return 1

	signature=$(get_magic_str "$1")

	case "$signature" in
	cs6b|\
	cs6c|\
	csys|\
	cr6b|\
	cr6c|\
	csro)
		;;
	*)
		echo "Invalid image. Signature $signature not recognized."
		return 1
		;;
	esac

	size=$(get_image "$1" | wc -c)
	if [ "$size" -le "$KERNEL_PART_SIZE" ]; then
		echo "Invalid image: $size bytes, no rootfs behind the kernel partition."
		return 1
	fi

	return 0
}

platform_do_upgrade() {
	local image="$1"
	local kernel_mtd rootfs_mtd

	kernel_mtd=$(find_mtd_part kernel)
	rootfs_mtd=$(find_mtd_part rootfs)

	if [ -z "$kernel_mtd" ] || [ -z "$rootfs_mtd" ]; then
		echo "Upgrade failed: kernel/rootfs partitions not found."
		return 1
	fi

	# mtd erases and writes only the explicitly named partition.
	get_image "$image" | dd bs=4096 count=$((KERNEL_PART_SIZE / 4096)) 2>/dev/null | \
		mtd write - kernel || return 1
	get_image "$image" | dd bs=4096 skip=$((KERNEL_PART_SIZE / 4096)) 2>/dev/null | \
		mtd -r write - rootfs || return 1
}
