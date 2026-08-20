#

#


#






#
# This is free software, licensed under the GNU General Public License v2.
#
include $(TOPDIR)/rules.mk

ARCH:=mipsel
BOARD:=rtkmipsel
BOARDNAME:=Realtek mipsel SOC
SUBTARGETS:=rtl8197f
FEATURES:=ramdisk squashfs usb
KERNEL_PATCHVER:=4.14

include $(INCLUDE_DIR)/target.mk

define Target/Description
	Build firmware images for Realtek RTL8197F based boards
endef

$(eval $(call BuildTarget))
