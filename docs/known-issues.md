# Known issues and release boundaries

This page describes the published 2026-08-19 RAM snapshot. Do not file a new bug for an item
already listed here unless your result adds materially different evidence.

## Security limitations

- **No root password is set.** SSH and LuCI must not be exposed to an untrusted network.
- **Both Wi-Fi APs use the public key `hh71vm12345`.** Change it for a private test, knowing
  that the change disappears when the RAM system is powered off.
- **Some vendor procfs controls still have overly broad permissions.** The release audit
  must reduce permissions on entries that can expose key material.
- **Logs can contain unique identifiers.** Redact MAC addresses, serial numbers, IMEI/IMSI,
  SIM data, phone numbers, messages, credentials, and keys before posting.

Use this build only on an isolated lab network.

## RAM-only behavior

- OpenWrt settings and files created in the running system disappear after power-off.
- The RAM image is not a flash installer. Prebuilt `fwupg` and `sysupgrade` images are not
  published, and the public loader has no flash-write command.
- The current source tree contains ongoing flash-support code, but using it is outside the
  public test scope.
- Settings changed through the modem UI act on the separate Qualcomm subsystem and may
  persist there. A Realtek/OpenWrt reboot is not guaranteed to undo them.

## Hardware coverage

The current build has been validated on one HH71VM. Other HH71/HH71VM board revisions,
regional variants, RF front ends, carrier variants, and flash layouts remain unverified.

The build selects these reference-unit values:

- SoC radio: `SOC_RFE_TYPE_1`;
- PCIe 5 GHz radio: `RTL8812FE`, slot 0, `SLOT_0_RFE_TYPE_0`;
- external gigabit PHY on switch port 0, MDIO address 6.

A unit with different hardware may boot but have reduced radio performance, unstable links,
or no networking. Report marker differences; do not attempt flash installation.

## Modem and LuCI limitations

- Modem control-channel preparation has occasionally taken roughly 3–9 minutes.
- Long multipart SMS messages are truncated or assembled in the wrong order. Do not use the
  current UI for important message handling.
- Long-term reconnect behavior after Qualcomm-side restart is not yet validated.
- Some radio/scan signal and mode fields in the UI still need audit or clearer handling.
- Long-term stability and paid SMS sending have not been validated.

## Network-driver quirks

`ip link` may not show Ethernet carrier correctly because the vendor driver does not update
the standard carrier state. Use:

```sh
cat /proc/rtl865x/port_status
cat /proc/eth0/link_status
```

The switch is named `switch0`:

```sh
swconfig list
swconfig dev switch0 show
```

Some vendor Wi-Fi proc counters are incomplete. In particular, `/proc/wlanX/sta_info` and
several fields under `/proc/wlanX/stats` may not reflect active traffic reliably. Prefer
`iwinfo`, DHCP leases, ARP entries, and an actual traffic test.

The two radio interfaces currently use the same default MAC behavior. Record observations,
but redact unique addresses in public reports.

## SSH and file transfer

The bundled Dropbear offers the legacy `ssh-rsa` host-key algorithm:

```text
ssh -o HostKeyAlgorithms=+ssh-rsa root@192.168.1.1
```

If a previous RAM boot used another host key:

```text
ssh-keygen -R 192.168.1.1
```

The image has no SFTP server. Use legacy SCP mode when required:

```text
scp -O local-file root@192.168.1.1:/tmp/
```

## Not yet independently reproduced

The included source state, build configuration, base revision, and feed revisions were
captured from the environment that produced the image. A second clean-checkout rebuild has
not yet independently reproduced the published SHA-256. See [sources and build
instructions](sources.md) for the exact verification target.
