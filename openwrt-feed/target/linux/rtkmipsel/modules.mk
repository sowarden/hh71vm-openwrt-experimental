# Kernel module packages for the rtkmipsel target.
#
# The vendor Wi-Fi driver is currently the only package here. Without this package,
# rtl8192cd.ko remains in build_dir and is not included in the root filesystem.
#
# It is a module rather than built-in so development iterations can use scp and
# insmod without rebuilding the image or repeating the WPS RAM-boot sequence.

define KernelPackage/rtl8192cd
  SUBMENU:=$(WIRELESS_MENU)
  TITLE:=Realtek RTL8192CD vendor driver (RTL8197F 2.4 GHz SoC radio)
  DEPENDS:=@TARGET_rtkmipsel
  KCONFIG:=CONFIG_RTL8192CD
  FILES:=$(LINUX_DIR)/drivers/net/wireless/realtek/rtl8192cd/rtl8192cd.ko
  AUTOLOAD:=$(call AutoLoad,50,rtl8192cd)
endef

define KernelPackage/rtl8192cd/description
 Realtek vendor Wi-Fi driver from SDK v3.4.14b (D-Link DIR-842E GPL archive),
 ported to Linux 4.14. This is not a cfg80211 driver; it is configured through
 private iwpriv ioctls and the custom /lib/netifd/wireless/rtl8192cd.sh handler.
endef

$(eval $(call KernelPackage,rtl8192cd))
