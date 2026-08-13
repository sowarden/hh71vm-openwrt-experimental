#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rtk_tftp_put.py — минимальный TFTP-клиент (RFC 1350, только WRQ/octet) для
заливки образов в консоль загрузчика Realtek `<RealTek>` (HH71VM,
Realtek-сторона).

ЗАЧЕМ СВОЙ КЛИЕНТ, А НЕ СТАНДАРТНЫЙ `tftp`
    Загрузчик отвечает ACK/DATA НЕ с порта 69 (куда пришёл WRQ), а с
    РАСТУЩЕГО TID, начинающегося с 2098 и увеличивающегося на 1 после каждой
    завершённой передачи (офлайн-разбор 2026-08-11, см.
    результат дизассемблирования загрузчика (разбор не входит в этот репозиторий), раздел
    «Сеть и TFTP»). Это корректное RFC-1350 поведение, но ПРОТИВОПОЛОЖНОЕ
    тому, что было у decoy-`tftp`-клиента ЖИВОЙ системы роутера (Трек 1,
    см. tftp_dump_mtd.py в этом же каталоге — там сервер обязан был отвечать
    с порта 69, иначе клиент роутера молчал). Здесь TID сервера вычитывается
    из ПЕРВОГО пришедшего ACK и используется для всех последующих пакетов
    этой же передачи — жёстко зашивать 69 или любой другой порт нельзя.

    ВАЖНО (тот же разбор): загрузчик проверяет ИМЯ файла ДО решения, что с
    ним делать: `boot.img` (точное совпадение) или любое имя, содержащее
    `nfjrom`, переключает его из «записать во флеш через burn_image» в
    «перейти на код в RAM» (`Jump to 0x...`, `jalr $t9`) — ПЕРЕД проверкой
    AUTOBURN. Такие имена здесь запрещены без явного флага.

ТРЕБОВАНИЕ К ЗАПУСКУ (как и у tftp_dump_mtd.py): входящие UDP-ответы с
произвольного TID покрываются только явным правилом Windows Firewall для
конкретного бинарника python.exe (Inbound, UDP, Any local port, профили
Private+Public). На этой машине это `C:\\Program Files\\Python39\\python.exe`
— запускать строго им, не через venv/pyenv с другим путём к интерпретатору.

ПРИМЕРЫ
    python rtk_tftp_put.py test-a.img --host 192.168.1.6 --name test-a.img
    python rtk_tftp_put.py boot.img --name boot.img --i-know-this-executes
"""

import argparse
import os
import socket
import struct
import sys
import time

OP_RRQ, OP_WRQ, OP_DATA, OP_ACK, OP_ERROR = 1, 2, 3, 4, 5
BLOCK_SIZE = 512
DEFAULT_HOST = "192.168.1.6"   # дефолтный IP консоли <RealTek> (bootloader-analysis.md)
DEFAULT_PORT = 69

# Имена, переключающие загрузчик на "Jump to 0x..." вместо записи во флеш
# (см. bootloader-analysis.md, раздел «Сеть и TFTP»). Сравнение здесь
# сознательно шире реального (case-insensitive), чем в самом загрузчике
# (byte-exact) — предохранитель должен блокировать с запасом, не впритык.
FORBIDDEN_NAME_EXACT = {"boot.img"}
FORBIDDEN_NAME_SUBSTR = ("nfjrom",)

LOGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tftp-put-logs")


class TftpError(RuntimeError):
    pass


def check_forbidden_name(name, override=False):
    """Бросает TftpError, если имя запрещено (см. FORBIDDEN_* выше), кроме
    override=True (--i-know-this-executes)."""
    if override:
        return
    lname = name.lower()
    if lname in FORBIDDEN_NAME_EXACT or any(s in lname for s in FORBIDDEN_NAME_SUBSTR):
        raise TftpError(
            "имя файла %r запрещено: загрузчик распознаёт boot.img/*nfjrom* и "
            "вместо записи во флеш ПЕРЕЙДЁТ на выполнение принятых данных как "
            "кода (см. bootloader-analysis.md, раздел «Сеть и TFTP»). "
            "Переименуйте файл, либо передайте override=True/"
            "--i-know-this-executes, если это осознанное намерение." % name)


def _pkt_wrq(filename, mode="octet"):
    return (struct.pack("!H", OP_WRQ) + filename.encode("ascii") + b"\x00"
            + mode.encode("ascii") + b"\x00")


def _pkt_data(block, payload):
    return struct.pack("!HH", OP_DATA, block & 0xFFFF) + payload


class _Logger:
    """Пишет каждый пакет в файл (всегда) и отдаёт в stdout только сводку +
    редкие контрольные точки — иначе на файле 500+ КБ (>1000 блоков)
    терминал утонет в построчном выводе."""

    def __init__(self, logfile, stdout_every=64):
        os.makedirs(LOGDIR, exist_ok=True)
        self.f = open(logfile, "a", encoding="utf-8")
        self.stdout_every = stdout_every
        self._last_stdout_block = -1

    def pkt(self, direction, block, extra=""):
        # time.strftime (в отличие от datetime.strftime) не понимает %f на
        # этой платформе (ValueError: Invalid format string) — миллисекунды
        # считаем вручную из time.time().
        now = time.time()
        ts = "%s.%03d" % (time.strftime("%H:%M:%S", time.localtime(now)), int(now * 1000) % 1000)
        line = "[%s] %s block=%s %s" % (ts, direction, block, extra)
        self.f.write(line + "\n")
        self.f.flush()

    def note(self, msg, to_stdout=True):
        line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
        self.f.write(line + "\n")
        self.f.flush()
        if to_stdout:
            print(msg)

    def progress(self, block, sent, total):
        if block - self._last_stdout_block >= self.stdout_every or sent >= total:
            print("  ... блок %d, %d/%d байт" % (block, sent, total))
            self._last_stdout_block = block

    def close(self):
        self.f.close()


def put(data, host=DEFAULT_HOST, port=DEFAULT_PORT, remote_name="upload.bin",
        timeout=2.0, retries=5, logfile=None, name_override=False):
    """Заливает bytes `data` на (host,port) под именем remote_name через
    TFTP WRQ/octet. Возвращает dict со статистикой: bytes, blocks, seconds,
    kbps, server_host, server_tid, retransmits."""
    check_forbidden_name(remote_name, override=name_override)

    if logfile is None:
        logfile = os.path.join(LOGDIR, "put-%s-%s.log"
                               % (time.strftime("%Y%m%d-%H%M%S"), remote_name.replace("/", "_")))
    log = _Logger(logfile)
    log.note("=== WRQ %r -> %s:%d (%d байт) ===" % (remote_name, host, port, len(data)))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    t0 = time.time()
    retransmits = 0
    server_addr = None

    try:
        # --- WRQ, ждём первый ACK — из него узнаём реальный TID сервера ---
        wrq = _pkt_wrq(remote_name)
        for attempt in range(1, retries + 1):
            log.pkt("SEND", "WRQ", "attempt=%d name=%r -> %s:%d" % (attempt, remote_name, host, port))
            sock.sendto(wrq, (host, port))
            try:
                pkt, addr = sock.recvfrom(65536)
            except socket.timeout:
                retransmits += 1
                continue
            op = struct.unpack("!H", pkt[:2])[0]
            if op == OP_ERROR:
                code = struct.unpack("!H", pkt[2:4])[0]
                msg = pkt[4:].split(b"\x00")[0]
                raise TftpError("сервер отклонил WRQ: code=%d msg=%r" % (code, msg))
            if op != OP_ACK:
                raise TftpError("ожидался ACK на WRQ, получен opcode=%d: %r" % (op, pkt[:16]))
            ack_block = struct.unpack("!H", pkt[2:4])[0]
            if ack_block != 0:
                raise TftpError("ACK на WRQ с неожиданным номером блока %d (ждали 0)" % ack_block)
            server_addr = addr
            log.pkt("RECV", 0, "ACK от %s:%d (TID сервера зафиксирован)" % server_addr)
            log.note("TID сервера = %d (латчен из первого ACK, НЕ порт %d)" % (server_addr[1], port))
            break
        else:
            raise TftpError("WRQ не подтверждён за %d попыток (timeout=%.1fs каждая) — "
                            "проверь ETH выполнен, кабель, Windows Firewall для python.exe"
                            % (retries, timeout))

        # --- DATA-блоки, строго на зафиксированный TID сервера ---
        block = 1
        sent = 0
        offset = 0
        while True:
            chunk = data[offset:offset + BLOCK_SIZE]
            pkt_out = _pkt_data(block, chunk)
            acked = False
            for attempt in range(1, retries + 1):
                log.pkt("SEND", block, "len=%d attempt=%d" % (len(chunk), attempt))
                sock.sendto(pkt_out, server_addr)
                try:
                    pkt, addr = sock.recvfrom(65536)
                except socket.timeout:
                    retransmits += 1
                    log.pkt("TIMEOUT", block, "attempt=%d, retransmit" % attempt)
                    continue
                op = struct.unpack("!H", pkt[:2])[0]
                if op == OP_ERROR:
                    code = struct.unpack("!H", pkt[2:4])[0]
                    msg = pkt[4:].split(b"\x00")[0]
                    raise TftpError("сервер прислал ERROR на блоке %d: code=%d msg=%r" % (block, code, msg))
                if op != OP_ACK:
                    log.pkt("IGNORE", block, "неожиданный opcode=%d" % op)
                    continue
                ack_block = struct.unpack("!H", pkt[2:4])[0]
                if ack_block != (block & 0xFFFF):
                    log.pkt("IGNORE", block, "ACK для блока %d, а не текущего — возможен дубликат" % ack_block)
                    continue
                if addr != server_addr:
                    log.pkt("WARN", block, "ACK пришёл с %s:%d, а не с зафиксированного %s:%d — принял всё равно"
                           % (addr[0], addr[1], server_addr[0], server_addr[1]))
                acked = True
                log.pkt("RECV", block, "ACK от %s:%d" % addr)
                break
            if not acked:
                raise TftpError("блок %d не подтверждён за %d попыток" % (block, retries))
            sent += len(chunk)
            offset += len(chunk)
            log.progress(block, sent, len(data))
            if len(chunk) < BLOCK_SIZE:
                break
            block = (block + 1) & 0xFFFF
    finally:
        sock.close()

    elapsed = time.time() - t0
    stats = dict(
        bytes=len(data),
        blocks=block,
        seconds=elapsed,
        kbps=(len(data) / 1024.0 / elapsed) if elapsed > 0 else 0.0,
        server_host=server_addr[0] if server_addr else None,
        server_tid=server_addr[1] if server_addr else None,
        retransmits=retransmits,
        logfile=logfile,
    )
    log.note("=== готово: %(bytes)d байт, %(blocks)d блоков, %(seconds).2fs, "
             "%(kbps).1f КБ/с, TID сервера=%(server_tid)s, ретрансмитов=%(retransmits)d ==="
             % stats)
    log.close()
    return stats


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="файл для заливки (обычно уже собранный rtk_mkimg.py образ)")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--name", default=None, help="имя файла для TFTP (по умолчанию — basename)")
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--i-know-this-executes", action="store_true",
                    help="разрешить запрещённые имена (boot.img/*nfjrom*) — они "
                         "переключают загрузчик на ВЫПОЛНЕНИЕ кода вместо записи")
    ap.add_argument("--log", default=None, help="путь к файлу лога (по умолчанию — auto в tftp-put-logs/)")
    args = ap.parse_args()

    with open(args.file, "rb") as f:
        data = f.read()
    remote_name = args.name or os.path.basename(args.file)

    stats = put(data, host=args.host, port=args.port, remote_name=remote_name,
               timeout=args.timeout, retries=args.retries, logfile=args.log,
               name_override=args.i_know_this_executes)

    print("bytes=%(bytes)d seconds=%(seconds).2f kbps=%(kbps).1f "
          "server_tid=%(server_tid)s retransmits=%(retransmits)d" % stats)
    print("лог: %s" % stats["logfile"])


if __name__ == "__main__":
    main()
