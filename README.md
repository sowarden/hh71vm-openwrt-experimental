# Experimental OpenWrt RAM boot for Alcatel LINKHUB HH71VM

This repository provides an **early OpenWrt build that runs from RAM** on the Realtek
subsystem of the Alcatel LINKHUB HH71VM (`RTL8197FS` + `RTL8812FE`). Its purpose is to
collect reproducible logs and compatibility results from HH71, HH71VM, and regional or
board-revision variants.

> [!IMPORTANT]
> This is a testing snapshot, not a production firmware release. It was verified on one
> physical HH71VM. Other variants are currently unverified — that is exactly what this
> community test is intended to discover.

## Start here

- To run the build, follow the [RAM boot guide](docs/installation.md).
- After any attempt, successful or not, submit a
  [compatibility report](https://github.com/sowarden/hh71vm-openwrt-experimental/issues/new/choose).
- For deeper checks, use the [testing and log collection guide](docs/testing.md).

## Safety boundary

The published image is loaded by the Realtek bootloader into RAM and is not an installer.
On the reference device, this path was tested without writing the Realtek SPI flash. A normal
power cycle boots the firmware already stored on the device.

The repository intentionally does **not** include prebuilt `fwupg` or `sysupgrade` images,
flash-writing tools, or public flash-install instructions. Flash installation will be
published only after the release audit and recovery path are considered safe enough for
general testing.

The source tree includes ongoing flash-support work because it is part of the current port,
but building or using flash images is outside the scope of this test release.

> [!WARNING]
> Testing requires opening the enclosure and using a **3.3 V USB-to-UART adapter**.
> Incorrect voltage, wiring, or handling can damage hardware. Do not connect the adapter's
> power pin to the router.

## Current RAM snapshot

Published image: `2026-08-19`, 4,043,561 bytes

SHA-256:
`4d4a329edbe034e431a12f4f57aa8c46c4f4fe51a4d1d161a852b6a9134691f7`

Verified on the reference HH71VM:

| Subsystem | Status |
|---|---|
| OpenWrt 19.07 / Linux 4.14.275 | Boots from RAM to a working system |
| UART and 128 MiB RAM detection | Working |
| Ethernet and external gigabit PHY | Working |
| 2.4 GHz Wi-Fi (`RTL8197FS`) | Working through UCI/netifd |
| 5 GHz Wi-Fi (`RTL8812FE`) | Working through UCI/netifd |
| Qualcomm USB mux and RNDIS WAN (`eth2`) | Working |
| Mobile Internet through the Qualcomm modem | Working on the reference device |
| LuCI and the custom HH71VM theme | Working |
| HH71VM modem-control pages | Working; known limitations remain |
| Persistent OpenWrt settings | Not available in this RAM build |
| Public flash installation | Not released |

The default test networks are:

| Band | SSID | Channel | Password |
|---|---|---|---|
| 2.4 GHz | `HH71VM` | 6 | `hh71vm12345` |
| 5 GHz | `HH71VM-5G` | 36 | `hh71vm12345` |

These credentials are public. Use the router only on an isolated test network and set a root
password in LuCI before exposing any interface to untrusted clients.

## Quick path

1. Connect a 3.3 V USB-to-UART adapter to the **Realtek-side** UART at `38400 8N1`.
2. Connect the router LAN port directly to the computer and set the computer to
   `192.168.1.50/24` with gateway `192.168.1.1`.
3. Install Python 3 and the required package:

   ```text
   python -m pip install -r tools/requirements.txt
   ```

4. Power on while holding WPS and wait for the `<RealTek>` prompt.
5. Close PuTTY or any other program using the serial port, then run:

   ```text
   python tools/ram_boot.py firmware/openwrt-rtkmipsel-rtl8197f-hh71vm-nfjrom.bin --port COM8
   ```

   Replace `COM8` with your real serial port. Linux and macOS users will normally use
   `python3` and a device such as `/dev/ttyUSB0`.

6. Open `http://192.168.1.1/`, test the required subsystems, and keep the generated UART log
   from `tools/ram-boot-logs/`.
7. Submit a compatibility report even if everything worked.

Do not improvise bootloader commands. The [full guide](docs/installation.md) includes the
pinout reference, checksum verification, success criteria, recovery, and troubleshooting.

## Reporting and privacy

Both positive and negative results are valuable. Reports should identify the visible board
revision, device model, region, stock firmware version, and exact image hash, then include
the UART log and requested diagnostic output.

Review every log before publishing it. Redact device-unique data you do not want public,
including full MAC addresses, serial numbers, IMEI/IMSI values, phone numbers, SMS content,
credentials, and keys. Attach searchable text, not screenshots of text.

## Known release limitations

- No root password is set in the image.
- Both Wi-Fi networks use a public default key.
- Long SMS handling is currently incorrect.
- Modem control can take several minutes to become ready after some boots.
- Long-term stability and other hardware revisions have not been validated.
- OpenWrt-side changes disappear after power-off, but settings changed on the Qualcomm modem
  side may persist there.

See the complete [known issues and security notes](docs/known-issues.md).

## Repository map

| Path | Purpose |
|---|---|
| [`docs/installation.md`](docs/installation.md) | Guided RAM boot procedure |
| [`docs/testing.md`](docs/testing.md) | Test matrix, log collection, and reporting |
| [`docs/known-issues.md`](docs/known-issues.md) | Current limitations and expected quirks |
| [`docs/sources.md`](docs/sources.md) | Source provenance and build instructions |
| [`docs/driver-reuse.md`](docs/driver-reuse.md) | Advanced port-reuse guidance and coupling |
| [`openwrt-feed/`](openwrt-feed/) | Current HH71VM source delta and build config |
| [`firmware/`](firmware/) | RAM image, manifest, and checksum |
| [`tools/ram_boot.py`](tools/ram_boot.py) | RAM-only loader and UART capture tool |
| [`CHANGELOG.md`](CHANGELOG.md) | Published snapshot history |

## Source and licenses

The source delta used for this image is included and its OpenWrt and feed revisions are
pinned in [docs/sources.md](docs/sources.md). A clean-room rebuild from those instructions
still needs independent verification before the release is mirrored widely.

The source tree contains components under their respective upstream licenses. Project
documentation and the RAM boot tool use a separate license. See
[LICENSING.md](LICENSING.md) for the repository map.
