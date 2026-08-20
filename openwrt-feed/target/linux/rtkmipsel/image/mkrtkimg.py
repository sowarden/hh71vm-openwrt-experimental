#!/usr/bin/env python3
"""Build Realtek RTL8197F firmware containers inside the OpenWrt tree.

The format was verified from the device boot code and vendor /bin/fwupg:

    16-byte big-endian header:
        sig[4] | startAddr(u32) | burnAddr(u32) | len(u32)
    body of ``len`` bytes whose final checksum bytes make the sum of 16-bit
    big-endian body words equal zero.

Both the ROM bootloader burn_image path and the stock /bin/fwupg checker use this
checksum. Relevant signatures:

    cr6c / cs6c: kernel; header and body are written to flash
    r6cr: root filesystem; fwupg writes only the body at rootfs offset zero

Commands:
    build      --sig --start --burn --body --out
    stamp      --file --out
    pad        --file --align [--out]
    concat     --out file...
    checksize  --file --max
"""

import argparse
import struct
import sys


BODY16 = ("cr6c", "cs6c", "r6cr", "boot")
BODY8 = ("w6cg",)


def sum16_be(data):
    total = 0
    for index in range(0, len(data) - 1, 2):
        total = (total + struct.unpack_from(">H", data, index)[0]) & 0xFFFF
    if len(data) & 1:
        total = (total + (data[-1] << 8)) & 0xFFFF
    return total


# The bootloader obtains the rootfs image length from squashfs word offset 8,
# byte-swaps it, adds SQFS_SUPER plus checksum bytes, and validates that span. In
# standard squashfs 4.0 the field is mkfs_time, while stock stores the body length
# there in reverse byte order. Without this stamp, the bootloader calculates a bogus
# multi-gigabyte span and never reaches the kernel. The stock reference used
# word@8=0x00725D80 for a 0x726002-byte body.
SQFS_SUPER = 640


def stamp_rootfs_len(body):
    """Write the rootfs length encoding expected by the HH71VM bootloader."""
    if body[:4] not in (b"hsqs", b"sqsh"):
        sys.exit("mkrtkimg: r6cr body is not squashfs; check the build")
    return body[:8] + struct.pack(">I", len(body) - SQFS_SUPER) + body[12:]


def append_checksum(body, signature):
    """Append checksum bytes that make the container body sum equal zero."""
    if signature in BODY8:
        padding = (-sum(body)) & 0xFF
        return body + bytes([padding])
    if len(body) & 1:
        body += b"\x00"
    if signature == "r6cr":
        body = stamp_rootfs_len(body)
    required = (-sum16_be(body)) & 0xFFFF
    return body + struct.pack(">H", required)


def cmd_stamp(arguments):
    """Prepare rootfs content for both r6cr and direct sysupgrade writing."""
    body = append_checksum(open(arguments.file, "rb").read(), "r6cr")
    open(arguments.out, "wb").write(body)
    print("mkrtkimg: stamped %s, body=%d" % (arguments.out, len(body)))


def cmd_build(arguments):
    body = open(arguments.body, "rb").read()
    if not arguments.body_final:
        body = append_checksum(body, arguments.sig)
    header = arguments.sig.encode("ascii") + struct.pack(
        ">III", arguments.start, arguments.burn, len(body)
    )
    blob = header + body
    if sum16_be(body) != 0 and arguments.sig in BODY16:
        sys.exit("mkrtkimg: checksum mismatch; image construction is broken")
    open(arguments.out, "wb").write(blob)
    print(
        "mkrtkimg: %s sig=%s start=0x%08x burn=0x%08x body=%d total=%d"
        % (
            arguments.out,
            arguments.sig,
            arguments.start,
            arguments.burn,
            len(body),
            len(blob),
        )
    )


def cmd_pad(arguments):
    data = open(arguments.file, "rb").read()
    if len(data) % arguments.align:
        data += b"\xff" * (arguments.align - len(data) % arguments.align)
    open(arguments.out or arguments.file, "wb").write(data)
    print("mkrtkimg: %s padded to %d bytes" % (arguments.out or arguments.file, len(data)))


def cmd_concat(arguments):
    with open(arguments.out, "wb") as output:
        for name in arguments.files:
            output.write(open(name, "rb").read())
    print("mkrtkimg: %s assembled from %d parts" % (arguments.out, len(arguments.files)))


def cmd_checksize(arguments):
    size = len(open(arguments.file, "rb").read())
    if size > arguments.max:
        sys.exit(
            "mkrtkimg: %s is %d bytes but the partition holds %d"
            % (arguments.file, size, arguments.max)
        )
    print(
        "mkrtkimg: %s = %d bytes, %d bytes spare"
        % (arguments.file, size, arguments.max - size)
    )


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="cmd", required=True)

    command = commands.add_parser("build")
    command.add_argument("--sig", required=True, choices=sorted(set(BODY16) | set(BODY8)))
    command.add_argument("--start", required=True, type=lambda value: int(value, 0))
    command.add_argument("--burn", required=True, type=lambda value: int(value, 0))
    command.add_argument("--body", required=True)
    command.add_argument("--out", required=True)
    command.add_argument(
        "--body-final",
        action="store_true",
        help="body already contains the rootfs stamp and checksum bytes",
    )
    command.set_defaults(func=cmd_build)

    command = commands.add_parser("stamp")
    command.add_argument("--file", required=True)
    command.add_argument("--out", required=True)
    command.set_defaults(func=cmd_stamp)

    command = commands.add_parser("pad")
    command.add_argument("--file", required=True)
    command.add_argument("--align", type=lambda value: int(value, 0), default=4096)
    command.add_argument("--out")
    command.set_defaults(func=cmd_pad)

    command = commands.add_parser("concat")
    command.add_argument("--out", required=True)
    command.add_argument("files", nargs="+")
    command.set_defaults(func=cmd_concat)

    command = commands.add_parser("checksize")
    command.add_argument("--file", required=True)
    command.add_argument("--max", required=True, type=lambda value: int(value, 0))
    command.set_defaults(func=cmd_checksize)

    arguments = parser.parse_args()
    arguments.func(arguments)


if __name__ == "__main__":
    main()
