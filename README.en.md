# OpenWrt for Alcatel LINKHUB HH71VM — experimental RAM-only build

[Русская версия](README.md) — more detailed; the documentation in `docs/` is in Russian.

An OpenWrt port for the Realtek side of the **Alcatel LINKHUB HH71VM** router (RTL8197FS SoC).
The build runs **from RAM** and **does not modify the flash memory** in any way.

> ## ⚠️ Read this first
>
> **This is a very early experimental build. It does not replace the stock firmware and is not
> installed onto the device.** The image is loaded into RAM and runs until the next power
> cycle. Turn the power off and the factory firmware comes back exactly as it was.
>
> **Not working:** 5 GHz Wi-Fi, the modem side (Qualcomm, SIM/LTE), web interface, and any
> persistence of settings across reboots.
>
> **You will need:** a USB-UART adapter and the willingness to open the case. There is no way
> to run this build without UART access.
>
> **No warranty of any kind.** The procedure itself does not touch the flash, but everything
> you do with your device is at your own risk.

## Why this is published

The port was developed and verified **on a single physical device**. Several decisions depend
on the specifics of that particular board: the RF front-end type, the external gigabit PHY on
switch port 0, and the location of MAC addresses in the flash service partition.

If your board revision or regional variant differs, behaviour may differ too — and there is no
way to find out except through other people's hardware. So the most valuable report is not
"everything works", but **any deviation** from what is described.

## Status

| Subsystem | State |
|---|---|
| Kernel boot, serial console | ✅ works |
| Ethernet (LAN port), bridge, DHCP server | ✅ works |
| SSH (dropbear) on `192.168.1.1` | ✅ works |
| Wi-Fi 2.4 GHz, access point, WPA2-AES | ✅ works |
| `opkg` present in the image | ⚠️ repositories never tested |
| Wi-Fi 5 GHz (RTL8812FE) | ❌ not implemented |
| Qualcomm modem (SIM, LTE) | ❌ out of scope for this port |
| Web interface (LuCI) | ❌ not included |
| Persistent settings | ❌ impossible: runs from RAM |

## Quick start

1. Connect a **3.3 V** USB-UART adapter to the Realtek side, **38400 8N1**.
2. Connect the LAN port to your computer, set the computer to **192.168.1.50/24**.
3. `pip install pyserial`
4. Power on the router **while holding the WPS button** — it stops at the `<RealTek>`
   bootloader prompt.
5. Run:

```
python tools/ram_boot.py firmware/openwrt-rtkmipsel-rtl8197f-hh71vm-nfjrom.bin --port COM8
```

(on Linux use something like `--port /dev/ttyUSB0`)

Then:

- SSH: `ssh -o HostKeyAlgorithms=+ssh-rsa root@192.168.1.1` — no password;
- Wi-Fi: SSID **`HH71VM-TEST`**, password **`hh71vm12345`**, channel 6.

Power-cycle the device to return to the factory firmware.

Note: plain `scp` will not work (no sftp-server in the build) — use `scp -O`.

## Reporting

Use the **Issues** tab. Two templates are available: a bug report, and a hardware report for
describing your board revision even when everything works. **A full UART log captured from
power-on is required** for almost any report; the script saves one automatically into
`tools/ram-boot-logs/`.

Please note that 5 GHz Wi-Fi, the modem and the web interface are known to be absent — reports
about them are not needed.

## Tooling limitation

Flash writing is **deliberately disabled** in `tools/rtk_romloader.py`. This repository exists
for exactly one scenario: running from RAM. Writing an unsuitable image to flash destroys the
bootloader irrecoverably, and recovery then requires a hardware programmer.

## Licence and sources

Built from OpenWrt 19.07 (Linux 4.14.275) plus Realtek vendor drivers taken from publicly
released GPL archives. Everything is **GPL-2.0** — see [LICENSE](LICENSE) and
[docs/sources.md](docs/sources.md) for the exact composition and how to obtain the sources.
