# Source provenance and build instructions

This repository includes the HH71VM source delta and the build configuration captured from
the environment that produced the published 2026-08-19 RAM image. Project-authored comments
and one diagnostic message were translated or removed for this English public snapshot, so
the public tree is not a byte-for-byte archive of the original build directory.

## Published artifact

| Item | Value |
|---|---|
| Image | `firmware/openwrt-rtkmipsel-rtl8197f-hh71vm-nfjrom.bin` |
| Size | 4,043,561 bytes |
| SHA-256 | `4d4a329edbe034e431a12f4f57aa8c46c4f4fe51a4d1d161a852b6a9134691f7` |
| Package manifest | `firmware/openwrt-rtkmipsel-rtl8197f-hh71vm.manifest` |
| Build config | `openwrt-feed/build.config` |
| Build-config SHA-256 | `bba8bed7004bece41372d111534ee7ec84edcb8e14eab7c2d43207321658f6c1` |

## Pinned upstream revisions

| Tree | Revision |
|---|---|
| OpenWrt | `1da2e82c1182a3fd681da5760be96821213afadd` |
| LuCI feed | `f25285a6c26e8776f153994704710cb8e51fad91` |
| packages feed | `6df6880800397ab3821572c6c5ad18e300374d9e` |

The build is based on OpenWrt 19.07 and Linux 4.14.275. The target architecture is
`mipsel_24kc`.

## HH71VM delta

`openwrt-feed/` contains:

- the `rtkmipsel/rtl8197f` target and HH71VM board support;
- RTL8197F BSP, UART, PCIe, GPIO, USB-mux, and SPI-NOR integration;
- the Realtek `rtknet` Ethernet/switch port and external-PHY setup;
- the Realtek `rtl8192cd` Wi-Fi port for RTL8197FS and RTL8812FE;
- UCI/netifd integration for both Wi-Fi radios;
- Qualcomm RNDIS WAN and modem-control integration;
- LuCI modem pages, HH71VM theme, and iwinfo compatibility patches;
- image construction scripts and the captured build configuration.

## Vendor-source provenance

The main donor sources were obtained from manufacturer-published GPL source archives:

| Component | Donor source |
|---|---|
| RTL8197F BSP and `rtknet` Ethernet/switch code | TP-Link Archer AX12 Realtek SDK v3.6.0 archive |
| `rtl8192cd` Wi-Fi code with PHYDM/HALMAC | D-Link DIR-842E Realtek SDK v3.4.14b archive |
| OpenWrt integration references | Community RTL8197F/OpenWrt trees, adapted and reviewed for this target |

The radio firmware data files are included in the vendor source trees in the form supplied
by the vendor and were not modified.

## Rebuild the RAM image

The original environment was Ubuntu 22.04 under WSL. OpenWrt 19.07 build scripts still rely
on Python 2 in parts of the configuration flow, so newer distributions may need additional
compatibility work.

The commands below describe the captured build layout. They have **not yet been independently
validated from a completely clean checkout**, so the final SHA comparison is a required
verification step rather than a promised bit-reproducible result.

```sh
git clone https://git.openwrt.org/openwrt/openwrt.git
cd openwrt
git checkout 1da2e82c1182a3fd681da5760be96821213afadd

./scripts/feeds update packages luci
git -C feeds/packages checkout 6df6880800397ab3821572c6c5ad18e300374d9e
git -C feeds/luci checkout f25285a6c26e8776f153994704710cb8e51fad91
./scripts/feeds install -a
```

From the parent directory containing this repository and the OpenWrt checkout:

```sh
rsync -a --delete \
  hh71vm-openwrt-experimental/openwrt-feed/target/linux/rtkmipsel/ \
  openwrt/target/linux/rtkmipsel/

rsync -a \
  hh71vm-openwrt-experimental/openwrt-feed/package/ \
  openwrt/package/

cp hh71vm-openwrt-experimental/openwrt-feed/build.config openwrt/.config
cd openwrt
make defconfig
make -j"$(nproc)"
```

The RAM artifact should appear under `bin/targets/rtkmipsel/rtl8197f/` with an
`-nfjrom.bin` suffix. Verify it:

```sh
sha256sum bin/targets/rtkmipsel/rtl8197f/*-nfjrom.bin
```

The release target is:

```text
4d4a329edbe034e431a12f4f57aa8c46c4f4fe51a4d1d161a852b6a9134691f7
```

If a clean build differs, preserve both manifests, the final `.config`, tool versions, and
the complete build log before changing source. Do not claim a reproduced build until the
cause of the difference is understood.

## Flash-image boundary

The current source includes later flash-support work because it is part of the same port.
The public test release intentionally provides only the `nfjrom` RAM artifact. Prebuilt
`fwupg` and `sysupgrade` files, flash tools, and public flash instructions are withheld until
the remaining release audit and recovery requirements are closed.

## License map

Files retain their upstream notices and licenses. See [LICENSING.md](../LICENSING.md) for the
repository-level map. This document records provenance and build state; it is not legal
advice.
