#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rtk_mkimg.py — сборка и разбор прошиваемых образов загрузчика Realtek RTL8197F
(консоль `<RealTek>` роутера Alcatel HH71VM, Realtek-сторона).

ФОРМАТ (реверсирован дизассемблированием загрузчика, см.
установлено дизассемблированием загрузчика):

    заголовок (16 байт, поля big-endian):
        sig[4] | startAddr(u32 BE) | burnAddr(u32 BE) | len(u32 BE)
    тело (len байт), в котором последние 1-2 байта — контрольная сумма,
    подобранная так, чтобы вся сумма (см. ниже) была равна нулю.

Сигнатура определяет:
    - как считается контрольная сумма (только тело / заголовок+тело / 8-бит);
    - пишется ли 16-байтный заголовок вместе с телом во флеш, или только тело
      (значения таблицы секций 0x80012DEC — здесь захардкожены как SECTIONS);
    - вызывает ли загрузчик перезагрузку после успешной прошивки этой секции.

ЗАЧЕМ
    Чтобы собрать образ для заливки по TFTP (`AUTOBURN`), не гадая на живом
    устройстве. Гейт корректности — self-test ниже: пересобранный стоковый
    образ ядра (`cr6c`) обязан побайтово совпасть с содержимым флеша.

ПРИМЕРЫ
    python rtk_mkimg.py selftest
    python rtk_mkimg.py build --sig r6cr --burn 0xB01000 --body payload.bin --out img.bin
    python rtk_mkimg.py parse img.bin
"""

import argparse
import os
import struct
import sys

# --- таблица секций (см. bootloader-analysis.md, 0x80012DEC) ---------------
# checksum: 'body16'  — 16-бит BE сумма тела (len байт) == 0
#           'all16'   — 16-бит BE сумма заголовка+тела (len+16 байт) == 0
#           'body8'   — 8-бит сумма тела == 0
# header_to_flash: True  — во флеш пишется 16-байтный заголовок + тело
#                  False — во флеш пишется только тело (заголовок в файле
#                          нужен лишь для того, чтобы загрузчик нашёл секцию)

SECTIONS = {
    "cs6c": dict(desc="Linux kernel",              checksum="body16", header_to_flash=True,  reboot=True),
    "cr6c": dict(desc="Linux kernel (root-fs)",     checksum="body16", header_to_flash=True,  reboot=True),
    "w6cg": dict(desc="Webpages",                   checksum="body8",  header_to_flash=True,  reboot=False),
    "r6cr": dict(desc="Root filesystem",             checksum="body16", header_to_flash=False, reboot=False),
    "boot": dict(desc="Boot code",                   checksum="body16", header_to_flash=False, reboot=True),
    "ALL1": dict(desc="Total Image",                 checksum="all16",  header_to_flash=False, reboot=True),
    "ALL2": dict(desc="Total Image (no check)",       checksum="all16",  header_to_flash=False, reboot=True),
}

DEFAULT_START_ADDR = {
    "cs6c": 0x80A00000,
    "cr6c": 0x80A00000,
}

DEFAULT_DUMP0 = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "hh71vm-dumps-and-files", "realtek-mtd-dumps-2026-08-10",
    "mtdblock0-boot_cfg_linux.bin",
)
DEFAULT_KERNEL_PAYLOAD = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "hh71vm-dumps-and-files", "realtek-mtd-dumps-2026-08-10",
    "extracted", "mtd0-carved", "kernel-payload.bin",
)


# --- заголовок ---------------------------------------------------------

def pack_header(sig, start_addr, burn_addr, length):
    if len(sig) != 4:
        raise ValueError("сигнатура должна быть ровно 4 байта: %r" % sig)
    return sig.encode("ascii") + struct.pack(">III", start_addr, burn_addr, length)


def unpack_header(data):
    if len(data) < 16:
        raise ValueError("нужно минимум 16 байт заголовка, получено %d" % len(data))
    sig = data[:4].decode("ascii", errors="replace")
    start_addr, burn_addr, length = struct.unpack(">III", data[4:16])
    return dict(sig=sig, start_addr=start_addr, burn_addr=burn_addr, length=length)


# --- контрольная сумма --------------------------------------------------

def sum16_be(data):
    """16-битная BE сумма по словам; нечётный хвостовой байт игнорируется
    (так делает и сам загрузчик — цикл идёт с шагом 2 до len с усечением)."""
    total = 0
    n = len(data) - (len(data) % 2)
    for i in range(0, n, 2):
        total = (total + struct.unpack(">H", data[i:i + 2])[0]) & 0xFFFF
    return total


def sum8(data):
    return sum(data) & 0xFF


def append_checksum(body_core, mode, header_prefix=b""):
    """Добавляет к body_core контрольные байты так, чтобы контрольная сумма
    (в режиме mode) стала равна нулю. header_prefix участвует в сумме только
    для mode='all16' (используется, только если предварительно известен
    финальный заголовок — см. build_image)."""
    if mode == "body16":
        if len(body_core) % 2 != 0:
            raise ValueError(
                "body16: длина тела до контрольной суммы должна быть чётной "
                "(получено %d байт) — иначе последний байт выпадет из суммы" % len(body_core))
        need = (0x10000 - sum16_be(body_core)) & 0xFFFF
        return body_core + struct.pack(">H", need)
    if mode == "body8":
        need = (0x100 - sum8(body_core)) & 0xFF
        return body_core + bytes([need])
    if mode == "all16":
        if len(body_core) % 2 != 0:
            raise ValueError("all16: тело до контрольной суммы должно быть чётной длины")
        base = sum16_be(header_prefix) + sum16_be(body_core)
        need = (0x10000 - (base & 0xFFFF)) & 0xFFFF
        return body_core + struct.pack(">H", need)
    raise ValueError("неизвестный режим контрольной суммы: %r" % mode)


def verify_checksum(body, mode, header_prefix=b""):
    if mode == "body16":
        return sum16_be(body) == 0
    if mode == "body8":
        return sum8(body) == 0
    if mode == "all16":
        return (sum16_be(header_prefix) + sum16_be(body)) & 0xFFFF == 0
    raise ValueError("неизвестный режим контрольной суммы: %r" % mode)


# --- сборка / разбор образа ---------------------------------------------

def build_image(sig, burn_addr, body_core, start_addr=None, checksum_already_present=False):
    """Возвращает bytes готового файла (заголовок + тело) для заливки по TFTP.

    body_core       — полезная нагрузка БЕЗ контрольных байт (обычный случай),
                       либо С уже готовыми контрольными байтами, если
                       checksum_already_present=True (тогда они не трогаются,
                       только проверяются).
    """
    if sig not in SECTIONS:
        raise ValueError("неизвестная сигнатура %r, известны: %s" % (sig, list(SECTIONS)))
    info = SECTIONS[sig]
    if start_addr is None:
        start_addr = DEFAULT_START_ADDR.get(sig, 0)

    if info["checksum"] == "all16":
        # финальная длина известна заранее (checksum добавляет 2 байта),
        # поэтому заголовок можно посчитать один раз и включить в сумму
        if checksum_already_present:
            body_final = body_core
        else:
            final_len = len(body_core) + 2
            header = pack_header(sig, start_addr, burn_addr, final_len)
            body_final = append_checksum(body_core, "all16", header_prefix=header)
        header = pack_header(sig, start_addr, burn_addr, len(body_final))
        return header + body_final

    if checksum_already_present:
        body_final = body_core
    else:
        body_final = append_checksum(body_core, info["checksum"])
    header = pack_header(sig, start_addr, burn_addr, len(body_final))
    return header + body_final


def parse_image(data, verify=True):
    hdr = unpack_header(data)
    sig = hdr["sig"]
    body = data[16:16 + hdr["length"]]
    if len(body) != hdr["length"]:
        raise ValueError("файл короче, чем указано в заголовке: нужно %d байт тела, есть %d"
                          % (hdr["length"], len(body)))
    result = dict(hdr)
    result["body"] = body
    result["known_section"] = sig in SECTIONS
    if sig in SECTIONS:
        info = SECTIONS[sig]
        result["desc"] = info["desc"]
        result["reboot_after"] = info["reboot"]
        result["header_written_to_flash"] = info["header_to_flash"]
        if verify:
            header_prefix = data[:16] if info["checksum"] == "all16" else b""
            result["checksum_ok"] = verify_checksum(body, info["checksum"], header_prefix)
    return result


# --- self-test: пересобрать стоковый образ ядра ---------------------------

def selftest(dump0_path=DEFAULT_DUMP0, payload_path=DEFAULT_KERNEL_PAYLOAD):
    print("=== self-test: пересборка стокового образа ядра (cr6c) ===")
    with open(dump0_path, "rb") as f:
        flash = f.read()
    header_flash = flash[0x30000:0x30010]
    hdr = unpack_header(header_flash)
    print("заголовок из флеша: sig=%r start=0x%08X burn=0x%08X len=0x%X"
          % (hdr["sig"], hdr["start_addr"], hdr["burn_addr"], hdr["length"]))
    assert hdr["sig"] == "cr6c", "неожиданная сигнатура в дампе: %r" % hdr["sig"]

    body_flash = flash[0x30010:0x30010 + hdr["length"]]

    with open(payload_path, "rb") as f:
        payload = f.read()
    assert payload == body_flash, (
        "kernel-payload.bin (%d байт) не совпадает с телом из флеша (%d байт) — "
        "проверь путь/актуальность экстракта" % (len(payload), len(body_flash)))

    # 1) проверка самой контрольной суммы (не зависит от build_image)
    ok = verify_checksum(body_flash, "body16")
    print("контрольная сумма тела из флеша сходится в 0: %s" % ok)
    assert ok, "контрольная сумма стокового тела не сходится — переосмыслить алгоритм"

    # 2) реальный тест build_image: отрезать последние 2 байта (checksum),
    #    пересчитать их заново и сравнить с оригиналом побайтово
    body_core = body_flash[:-2]
    original_checksum_bytes = body_flash[-2:]
    rebuilt_body = append_checksum(body_core, "body16")
    rebuilt_checksum_bytes = rebuilt_body[-2:]
    print("контрольные байты оригинала: %s, пересчитанные: %s"
          % (original_checksum_bytes.hex(), rebuilt_checksum_bytes.hex()))
    assert rebuilt_checksum_bytes == original_checksum_bytes, (
        "мой append_checksum даёт другие байты, чем стоковый образ — "
        "алгоритм суммы неверен или неоднозначен (могут существовать разные "
        "пары байт с суммой 0)")

    # 3) полная сборка через build_image и побайтовое сравнение с флешем
    full = build_image("cr6c", hdr["burn_addr"], body_core,
                        start_addr=hdr["start_addr"])
    expected = header_flash + body_flash
    assert full == expected, "пересобранный образ не совпадает с флешем побайтово!"
    print("ПОЛНОЕ ПОБАЙТОВОЕ СОВПАДЕНИЕ: пересобранный образ (%d байт) == флеш 0x30000..0x%X"
          % (len(full), 0x30000 + len(full)))
    print("=== self-test PASSED ===")
    return True


# --- CLI ------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("selftest", help="пересобрать стоковый cr6c и сверить с флешем")

    p = sub.add_parser("build", help="собрать образ для заливки")
    p.add_argument("--sig", required=True, choices=list(SECTIONS))
    p.add_argument("--burn", required=True, help="burnAddr, hex (напр. 0xB01000)")
    p.add_argument("--start", default=None, help="startAddr, hex (по умолчанию 0)")
    p.add_argument("--body", required=True, help="файл с полезной нагрузкой (без checksum)")
    p.add_argument("--body-has-checksum", action="store_true",
                    help="тело уже содержит контрольные байты — не трогать их, только проверить")
    p.add_argument("--out", required=True)

    p = sub.add_parser("parse", help="разобрать готовый образ")
    p.add_argument("image")

    args = ap.parse_args()

    if args.cmd == "selftest":
        ok = selftest()
        sys.exit(0 if ok else 1)

    elif args.cmd == "build":
        with open(args.body, "rb") as f:
            body_core = f.read()
        burn_addr = int(args.burn, 0)
        start_addr = int(args.start, 0) if args.start is not None else None
        img = build_image(args.sig, burn_addr, body_core, start_addr=start_addr,
                          checksum_already_present=args.body_has_checksum)
        with open(args.out, "wb") as f:
            f.write(img)
        info = SECTIONS[args.sig]
        print("собрано: %s (%s), burnAddr=0x%X, тело=%d байт, файл=%d байт"
              % (args.sig, info["desc"], burn_addr, len(body_core), len(img)))
        print("во флеш попадёт: %s, автоперезагрузка после: %s"
              % ("заголовок+тело" if info["header_to_flash"] else "только тело",
                 info["reboot"]))
        print("-> %s" % args.out)

    elif args.cmd == "parse":
        with open(args.image, "rb") as f:
            data = f.read()
        r = parse_image(data)
        print("sig=%r  known=%s" % (r["sig"], r["known_section"]))
        print("startAddr=0x%08X  burnAddr=0x%08X  len=0x%X (%d)"
              % (r["start_addr"], r["burn_addr"], r["length"], r["length"]))
        if r["known_section"]:
            print("описание: %s" % r["desc"])
            print("во флеш попадёт: %s"
                  % ("заголовок+тело" if r["header_written_to_flash"] else "только тело"))
            print("автоперезагрузка после прошивки: %s" % r["reboot_after"])
            print("контрольная сумма сходится: %s" % r["checksum_ok"])


if __name__ == "__main__":
    main()
