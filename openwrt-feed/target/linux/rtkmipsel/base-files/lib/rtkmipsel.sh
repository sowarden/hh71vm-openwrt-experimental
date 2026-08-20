#!/bin/sh
#
# Detect the board from the /proc/cpuinfo machine string registered by
# arch/mips/rtl8197f/mach-hh71vm.c.
#
# The Realtek subsystem identifies the HH71 family, not a precise retail model. The
# Qualcomm-side modem service refines /tmp/sysinfo/model when it can query that side.

RTKMIPSEL_BOARD_NAME=
RTKMIPSEL_MODEL=

rtkmipsel_board_detect() {
	local machine
	local name

	machine=$(awk 'BEGIN{FS="[ \t]+:[ \t]"} /machine/ {print $2}' /proc/cpuinfo)

	case "$machine" in
	*"HH71"*)
		name="hh71vm"
		;;
	esac

	[ -z "$name" ] && name="unknown"

	[ -z "$RTKMIPSEL_BOARD_NAME" ] && RTKMIPSEL_BOARD_NAME="$name"
	[ -z "$RTKMIPSEL_MODEL" ] && RTKMIPSEL_MODEL="$machine"

	[ -e "/tmp/sysinfo/" ] || mkdir -p "/tmp/sysinfo/"

	echo "$RTKMIPSEL_BOARD_NAME" > /tmp/sysinfo/board_name
	echo "$RTKMIPSEL_MODEL" > /tmp/sysinfo/model
}
