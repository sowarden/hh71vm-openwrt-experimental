#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ram_boot.py — запуск образа из ОЗУ на Realtek-стороне HH71VM, без записи во флеш.

ЧТО ЭТО ДЕЛАЕТ

ROM-загрузчик `<RealTek>` проверяет имя принимаемого по TFTP файла ДО того, как
решить, что с ним делать: если имя содержит подстроку `nfjrom` (или равно ровно
`boot.img`), он НЕ вызывает `burn_image`, а печатает `Jump to 0x...` и передаёт
управление на принятые данные как на код (`jalr $t9`, 0x8000216C). Проверка имени
идёт РАНЬШЕ проверки `AUTOBURN` — установлено дизассемблированием загрузчика.

Отсюда весь сценарий: `ETH` -> `LOADADDR` -> `AUTOBURN 0` -> TFTP-заливка файла с
`nfjrom` в имени -> чтение консоли, пока грузится ядро. Флеш при этом не
затрагивается вообще; выключение питания возвращает устройство к стоку.

ПРЕДОХРАНИТЕЛИ (перевёрнутые относительно rtk_romloader.py)

В обычном режиме (`rtk_romloader.py tftp`) опасны имена с `nfjrom` — они означают
исполнение вместо записи, и заливщик их отклоняет. Здесь всё наоборот: опасно имя
БЕЗ `nfjrom`, потому что тогда загрузчик воспримет файл как образ для флеша.
Поэтому скрипт:
  - отказывается работать, если в имени нет `nfjrom`;
  - всё равно ставит `AUTOBURN 0` — вторая независимая страховка на случай, если
    имя почему-то не распознается;
  - не умеет отправить ни одной команды записи во флеш (`FLW`/`ERASECHIP`
    отклоняются самим `RomLoader`).

ПРО АДРЕС ЗАГРУЗКИ

По умолчанию `0x84000000` — ровно тот адрес, по которому слинкован наш
lzma-loader (`LZMA_TEXT_START` в openwrt-feed/target/linux/rtkmipsel/image/Makefile).
При другом LOADADDR прыжок уйдёт не туда. Адрес кэшируемый (KSEG0), и это
безопасно: перед `jalr` загрузчик сбрасывает кэши целиком — `cache 1` (Index
Writeback Inv D) по всем 32 КБ D-кэша и инвалидация I-кэша (0x80009D80/0x80009D50,
проверено дизассемблером).

ТРЕБОВАНИЕ К ЗАПУСКУ

Как и у остальных сетевых скриптов здесь: входящие UDP с произвольного TID
покрыты правилом Windows Firewall только для конкретного пути к интерпретатору.
Запускать строго `"C:\\Program Files\\Python39\\python.exe"`.

Устройство должно уже стоять в приглашении `<RealTek>` (питание с удержанием WPS).

ПРИМЕРЫ
    python ram_boot.py openwrt-...-nfjrom.bin
    python ram_boot.py образ.bin --uart-seconds 120 --loadaddr 0x84000000
    python ram_boot.py --listen-only --uart-seconds 60      # просто слушать консоль
"""

import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtk_romloader
import rtk_tftp_put

DEFAULT_LOADADDR = 0x84000000
REQUIRED_NAME_SUBSTR = "nfjrom"

LOGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ram-boot-logs")


def check_name_executes(name):
    """Обратный предохранитель: без `nfjrom` в имени загрузчик будет считать файл
    образом для флеша, а не кодом. Для этого скрипта такое имя — ошибка."""
    if REQUIRED_NAME_SUBSTR not in name.lower():
        raise SystemExit(
            "ОТКАЗ: в имени %r нет подстроки %r.\n"
            "Загрузчик распознаёт режим 'выполнить из ОЗУ' ИМЕННО по имени файла. "
            "Без неё он воспримет файл как образ для записи во флеш — а этот скрипт "
            "предназначен ровно для обратного. Переименуйте файл."
            % (name, REQUIRED_NAME_SUBSTR))


class Tee:
    """Пишет и в stdout (чтобы видеть загрузку вживую), и в файл лога."""

    def __init__(self, path):
        self.fh = open(path, "a", encoding="utf-8", newline="")
        self.path = path

    def write(self, text):
        # Консоль на ранней загрузке легко отдаёт мусорные байты (не тот битрейт,
        # обрывки). Падать на UnicodeEncodeError посреди захвата загрузки нельзя —
        # именно этот вывод мы и пришли собрать.
        enc = sys.stdout.encoding or "ascii"
        sys.stdout.write(text.encode(enc, "replace").decode(enc, "replace"))
        sys.stdout.flush()
        self.fh.write(text)
        self.fh.flush()

    def note(self, text):
        self.write("\n*** %s\n" % text)

    def close(self):
        self.fh.close()


def stream_uart(rl, tee, seconds, stop_when_quiet=None):
    """Читает консоль `seconds` секунд, печатая всё по мере поступления.
    Если задан `stop_when_quiet` — досрочно выходит после стольких секунд тишины."""
    deadline = time.time() + seconds
    last = time.time()
    while time.time() < deadline:
        chunk = rl.read_quiet(quiet_ms=200, max_wait_s=1.0)
        if chunk:
            tee.write(chunk.decode("latin-1"))
            last = time.time()
        elif stop_when_quiet and (time.time() - last) >= stop_when_quiet:
            tee.note("тишина на линии %.0f с — прекращаю чтение" % stop_when_quiet)
            return


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?", help="файл образа (имя должно содержать nfjrom)")
    ap.add_argument("--port", default=rtk_romloader.PORT_DEFAULT)
    ap.add_argument("--baud", type=int, default=rtk_romloader.BAUD_DEFAULT)
    ap.add_argument("--host", default=rtk_tftp_put.DEFAULT_HOST,
                    help="IP консоли загрузчика (его безусловно ставит ETH)")
    ap.add_argument("--name", default=None,
                    help="имя файла для TFTP (по умолчанию basename образа)")
    ap.add_argument("--loadaddr", default=hex(DEFAULT_LOADADDR),
                    help="адрес приёма и точки входа, hex (по умолчанию 0x84000000)")
    ap.add_argument("--skip-eth", action="store_true",
                    help="не поднимать сеть заново (если ETH уже выполнялась в этом включении)")
    ap.add_argument("--uart-seconds", type=float, default=90.0,
                    help="сколько секунд читать консоль после передачи")
    ap.add_argument("--listen-only", action="store_true",
                    help="ничего не отправлять, только слушать консоль")
    args = ap.parse_args()

    os.makedirs(LOGDIR, exist_ok=True)
    tee = Tee(os.path.join(LOGDIR, "ramboot-%s.log" % time.strftime("%Y%m%d-%H%M%S")))
    tee.note("лог: %s" % tee.path)

    if args.listen_only:
        with rtk_romloader.RomLoader(port=args.port, baud=args.baud) as rl:
            tee.note("режим прослушивания, %.0f с" % args.uart_seconds)
            stream_uart(rl, tee, args.uart_seconds)
        tee.close()
        return

    if not args.image:
        raise SystemExit("нужен путь к образу (или --listen-only)")

    remote_name = args.name or os.path.basename(args.image)
    check_name_executes(remote_name)

    with open(args.image, "rb") as f:
        data = f.read()

    loadaddr = int(args.loadaddr, 16)
    tee.note("образ %s — %d байт" % (args.image, len(data)))
    tee.note("LOADADDR 0x%08X, имя для TFTP %r, хост %s" % (loadaddr, remote_name, args.host))
    tee.note("флеш НЕ затрагивается: имя с nfjrom отключает burn_image, плюс AUTOBURN 0")

    with rtk_romloader.RomLoader(port=args.port, baud=args.baud) as rl:
        tee.write(rl.send_raw(""))          # приглашение, заодно проверка связи

        if not args.skip_eth:
            tee.note("ETH — поднимаю сеть загрузчика")
            tee.write(rl.cmd_eth())

        tee.note("LOADADDR")
        tee.write(rl.cmd_loadaddr(loadaddr))
        tee.note("AUTOBURN 0 (страховка: запись во флеш выключена)")
        tee.write(rl.cmd_autoburn(0))

        result = {}

        def _run_tftp():
            try:
                result["stats"] = rtk_tftp_put.put(
                    data, host=args.host, remote_name=remote_name, name_override=True)
            except Exception as exc:            # noqa: BLE001 — нужен любой сбой заливки
                result["error"] = exc

        tee.note("TFTP-заливка пошла; дальше консоль должна показать 'Jump to 0x%X'" % loadaddr)
        th = threading.Thread(target=_run_tftp, name="tftp-put", daemon=True)
        th.start()

        while th.is_alive():
            chunk = rl.read_quiet(quiet_ms=200, max_wait_s=1.0)
            if chunk:
                tee.write(chunk.decode("latin-1"))
        th.join(timeout=5.0)

        if "error" in result:
            tee.note("TFTP НЕ УДАЛАСЬ: %s" % result["error"])
            stream_uart(rl, tee, 10.0)
            tee.close()
            raise SystemExit(1)

        st = result["stats"]
        tee.note("TFTP: %d байт за %.1f с (%.0f кбит/с), TID сервера %s, ретрансмиссий %s"
                 % (st["bytes"], st["seconds"], st["kbps"], st["server_tid"], st["retransmits"]))
        tee.note("читаю консоль %.0f с" % args.uart_seconds)
        stream_uart(rl, tee, args.uart_seconds)

    tee.note("лог сохранён: %s" % tee.path)
    tee.close()


if __name__ == "__main__":
    main()
