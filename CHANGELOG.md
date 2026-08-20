# Changelog

Published images are identified by their SHA-256 digest from `firmware/SHA256SUMS`.

## 2026-08-19 — current RAM test snapshot

SHA-256:
`4d4a329edbe034e431a12f4f57aa8c46c4f4fe51a4d1d161a852b6a9134691f7`

Verified on one physical HH71VM:

- OpenWrt 19.07 / Linux 4.14.275 boots from RAM;
- Ethernet and the external gigabit PHY work;
- 2.4 GHz `RTL8197FS` and 5 GHz `RTL8812FE` Wi-Fi work through UCI/netifd;
- the Qualcomm USB mux exposes RNDIS as `eth2` and mobile Internet works;
- LuCI, the HH71VM theme, modem-control pages, and Wi-Fi client list work;
- the corresponding source implementation and captured build configuration are included.

Known limitations are tracked in [`docs/known-issues.md`](docs/known-issues.md). No prebuilt
flash-install or sysupgrade image is published.

## 2026-08-13 — first public RAM test snapshot

SHA-256:
`70fe5aeea90e3f2e4ab8a9e1148dac5a504efab8fd717f362257a30cf43acf64`

This historical image added automatic 2.4 GHz Wi-Fi startup on top of RAM boot, Ethernet,
DHCP, and SSH. It has been superseded and is no longer included in `firmware/`.
