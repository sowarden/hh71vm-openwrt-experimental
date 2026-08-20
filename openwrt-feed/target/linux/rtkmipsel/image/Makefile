#

#


#




#

#




#








#



#
# This is free software, licensed under the GNU General Public License v2.
#
include $(TOPDIR)/rules.mk
include $(INCLUDE_DIR)/image.mk


LZMA_TEXT_START := 0x84000000


FLASH_TEXT_START := 0x80A00000

KERNEL_LOADADDR := 0x80000000



#   0x000000 boot 128k | 0x020000 hwsetting 16k | 0x024000 config 48k
#   0x030000 kernel 2880k | 0x300000 rootfs 4096k | 0x700000 rootfs_data 5120k




KERNEL_PART_OFFSET := 0x30000
KERNEL_PART_SIZE := 2949120
ROOTFS_PART_OFFSET := 0x300000
ROOTFS_PART_SIZE := 4194304

MKRTKIMG := python3 $(TOPDIR)/target/linux/rtkmipsel/image/mkrtkimg.py



RAMFS_MAX_SIZE := 67108864








KERNEL_CMDLINE := board=HH71VM console=ttyS0,38400 mtdparts=m25p80:128k(boot),16k(hwsetting),48k(config),2880k(kernel),4096k(rootfs),5120k(rootfs_data),4096k(vendor_jffs2) root=/dev/mtdblock4 rootfstype=squashfs

define test
$(shell test $(1) $(2) $(3) && echo 1)
endef

define filesize
$(shell stat -L -c %s $1)
endef

LOADER_MAKE := $(NO_TRACE_MAKE) -C lzma-loader KDIR=$(KDIR) LINUX_DIR=$(LINUX_DIR)

define Build/Clean
	$(LOADER_MAKE) clean
endef



define Image/BuildLoader
	$(LOADER_MAKE) LOADER=$(1).bin \
		KERNEL_CMDLINE="$(KERNEL_CMDLINE)" \
		LZMA_TEXT_START=$(if $(3),$(3),$(LZMA_TEXT_START)) \
		LOADADDR=$(KERNEL_LOADADDR) \
		LOADER_DATA="$(KDIR)/$(2)" \
		BOARD="hh71vm" \
		compile loader.bin
endef

define Image/Prepare/initramfs
	$(if $(call test,$(call filesize,$(KDIR)/vmlinux-initramfs),-gt,$(RAMFS_MAX_SIZE)),\
		$(error $(KDIR)/vmlinux-initramfs bigger than $(RAMFS_MAX_SIZE) bytes))
	$(STAGING_DIR_HOST)/bin/lzma e $(KDIR)/vmlinux-initramfs -lc1 -lp2 -pb2 \
		$(KDIR)/vmlinux-initramfs.bin.lzma
	$(call Image/BuildLoader,loader-$(SUBTARGET)-hh71vm-ramfs,vmlinux-initramfs.bin.lzma)
endef



define Image/Prepare/flash
	$(STAGING_DIR_HOST)/bin/lzma e $(KDIR)/vmlinux -lc1 -lp2 -pb2 \
		$(KDIR)/vmlinux.bin.lzma
	$(call Image/BuildLoader,loader-$(SUBTARGET)-hh71vm-flash,vmlinux.bin.lzma,$(FLASH_TEXT_START))
endef

define Image/Prepare
	$(if $(CONFIG_TARGET_ROOTFS_INITRAMFS),$(call Image/Prepare/initramfs))
	$(if $(CONFIG_TARGET_ROOTFS_SQUASHFS),$(call Image/Prepare/flash))
endef

define Image/Build/Initramfs
	$(CP) $(KDIR)/loader-$(SUBTARGET)-hh71vm-ramfs.bin \
		$(BIN_DIR)/$(IMG_PREFIX)-hh71vm-nfjrom.bin
endef













define Image/Build/squashfs
	$(MKRTKIMG) build --sig cr6c --start $(FLASH_TEXT_START) --burn $(KERNEL_PART_OFFSET) \
		--body $(KDIR)/loader-$(SUBTARGET)-hh71vm-flash.bin \
		--out $(KDIR)/hh71vm-kernel-cr6c.bin
	$(MKRTKIMG) pad --file $(KDIR)/root.squashfs --align 4096 \
		--out $(KDIR)/hh71vm-root.squashfs
	$(MKRTKIMG) checksize --file $(KDIR)/hh71vm-kernel-cr6c.bin --max $(KERNEL_PART_SIZE)
	$(MKRTKIMG) stamp --file $(KDIR)/hh71vm-root.squashfs \
		--out $(KDIR)/hh71vm-root-stamped.bin
	$(MKRTKIMG) checksize --file $(KDIR)/hh71vm-root-stamped.bin --max $(ROOTFS_PART_SIZE)
	$(MKRTKIMG) pad --file $(KDIR)/hh71vm-kernel-cr6c.bin --align $(KERNEL_PART_SIZE) \
		--out $(KDIR)/hh71vm-kernel-padded.bin
	$(MKRTKIMG) concat --out $(BIN_DIR)/$(IMG_PREFIX)-hh71vm-sysupgrade.bin \
		$(KDIR)/hh71vm-kernel-padded.bin $(KDIR)/hh71vm-root-stamped.bin
	$(MKRTKIMG) build --sig r6cr --start 0 --burn $(ROOTFS_PART_OFFSET) \
		--body $(KDIR)/hh71vm-root-stamped.bin --body-final \
		--out $(KDIR)/hh71vm-rootfs-r6cr.bin
	$(MKRTKIMG) concat --out $(BIN_DIR)/$(IMG_PREFIX)-hh71vm-fwupg.bin \
		$(KDIR)/hh71vm-kernel-cr6c.bin $(KDIR)/hh71vm-rootfs-r6cr.bin
endef

define Image/Build
	$(call Image/Build/$(1),$(1))
endef

$(eval $(call BuildImage))
