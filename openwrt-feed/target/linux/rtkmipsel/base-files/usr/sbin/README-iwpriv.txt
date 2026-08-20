iwpriv is included here as a prebuilt bring-up binary.

rtl8192cd is configured through private Wireless Extensions ioctls rather than
cfg80211/nl80211, so it requires iwpriv from wireless_tools.29. The binary was built from
the vendor-published wireless_tools.29 source in the AX12 Realtek SDK v3.6.0 using the same
toolchain as the image.

The preferred long-term solution is a normal OpenWrt package or the pinned packages feed.
