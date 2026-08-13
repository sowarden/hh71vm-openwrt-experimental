#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rtk_romloader.py — драйвер консоли загрузчика Realtek `<RealTek>` (UART, HH71VM,
Realtek-сторона) для чтения/записи флеша через `FLR`/`FLW`.

СЕМАНТИКА КОМАНД — см. результат дизассемблирования загрузчика (разбор не входит в этот репозиторий)
(результат дизассемблирования, Фаза 0). Кратко, что важно для этого драйвера:

    - Команды шлются голым `\r` (без `\n`) — иначе лишний `\n` в очереди приёма
      съедается загрузчиком как ответ на подтверждение (Y/N) и даёт `Abort!`.
    - `FLW <flash_off> <ram_src> <len>` — 3 аргумента hex, БЕЗ проверки argc.
      Сам стирает все 4КБ-сектора диапазона перед записью.
    - `ERASECHIP <0|1>` стирает 16 МБ по-настоящему — этот скрипт физически не
      умеет её отправить (`_check_forbidden()`, проверяется на каждой отправке).
    - `ERASESECTOR` — пустая заглушка, здесь не реализована (бессмысленно).
    - IP устройства по умолчанию 192.168.1.6, адрес приёма TFTP 0xA0A00000.
    - `ETH` ОБЯЗАТЕЛЕН перед любым TFTP (флаг готовности сети взводится только
      внутри её обработчика) и безусловно перезаписывает IP/MAC — вызывать
      строго до `IPCONFIG`. Разделитель аргументов консоли — ПРОБЕЛ, не
      двоеточие (см. `cmd_ipconfig`/`cmd_loadaddr`).

ПРЕДОХРАНИТЕЛИ (в коде, не «на внимательность»):
    - `write_flash()`/`cmd_flw()` отклоняют адрес ДО отправки в порт, если он не
      входит в белый список `DEFAULT_ALLOWED_WRITE_RANGES` (по умолчанию —
      только хвост mtd1, `0x00A27000`-`0x00BFFFFF`, который весь `0xFF` и не
      используется системой).
    - `tftp`-подкоманда (заливка через AUTOBURN) отклоняет образ ДО передачи,
      если его `burnAddr..burnAddr+len` не входит в тот же белый список — это
      единственная защита для пути TFTP+AUTOBURN, т.к. сам загрузчик область
      записи вообще не проверяет (см. bootloader-analysis.md).
    - Любая команда, содержащая `ERASECHIP` (в любом регистре), отклоняется на
      уровне низкоуровневой отправки — обойти это можно только редактируя сам
      скрипт, не аргументами командной строки.
    - Имена файлов `boot.img`/`*nfjrom*` для TFTP отклоняются `rtk_tftp_put.py`
      (переключают загрузчик на исполнение кода вместо записи во флеш).
    - Перед реальной записью — печать «что, куда, сколько» и требование явного
      `--yes`/интерактивного подтверждения (если не передан `--yes`).
    - Весь обмен пишется в лог-файл (путь печатается при старте).

ТРЕБОВАНИЯ
    pip install pyserial
    rtk_mkimg.py и rtk_tftp_put.py — в той же директории (используются как модули)

ПРИМЕРЫ
    python rtk_romloader.py info                                    # FLI, приглашение
    python rtk_romloader.py eth                                     # поднять сеть загрузчика
    python rtk_romloader.py ipconfig                                # текущий IP (после eth)
    python rtk_romloader.py read 0x00B00000 256 --out dump.bin       # FLR+DW
    python rtk_romloader.py write 0x00B00000 --pattern 0011223344556677 --yes
    python rtk_romloader.py write 0x00B00000 --file payload.bin --yes
    python rtk_romloader.py verify 0x00B00000 --file payload.bin     # читает и сверяет
    python rtk_romloader.py tftp test-a.img --autoburn 0             # сухой прогон, без записи
    python rtk_romloader.py tftp test-a.img --autoburn 1 --verify    # заливка + запись + readback
"""

import argparse
import os
import re
import sys
import threading
import time

try:
    import serial
except ImportError:
    serial = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rtk_mkimg      # сборка/разбор образов — переиспользуем parse_image/unpack_header
import rtk_tftp_put    # TFTP WRQ-клиент с латчингом TID

PORT_DEFAULT = "COM8"
BAUD_DEFAULT = 38400

# Хвост mtd1 (0x300000-0xBFFFFF во флеше): squashfs заканчивается на 0xA256BE,
# всё дальше до 0xBFFFFF — стёртая (0xFF) неиспользуемая область (см.
# bootloader-analysis.md и разведку дампов). Это единственный диапазон,
# разрешённый на запись без явного расширения белого списка в коде.
DEFAULT_ALLOWED_WRITE_RANGES = [(0x00A27000, 0x00BFFFFF)]

FLASH_SIZE = 16 * 1024 * 1024

LOGDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "romloader-logs")


class SafetyError(RuntimeError):
    pass


def check_range_allowed(addr, length, allowed_ranges):
    """Проверяет, что [addr, addr+length) целиком входит в один из
    allowed_ranges (список (lo, hi), включительно) и не выходит за физический
    размер флеша. При успехе ничего не возвращает; иначе бросает SafetyError.

    Вынесено в свободную функцию (тот же принцип, что и у parse_dw_output/
    parse_db_output ниже) — используется и `_check_write_range()` (путь
    FLW), и `send_image_via_tftp()` (путь TFTP+AUTOBURN, где сам загрузчик
    область записи вообще не проверяет — это единственная защита), и
    проверяется юнит-тестом без реального COM-порта."""
    # --- В ПУБЛИЧНОЙ СБОРКЕ ЗАПИСЬ ВО ФЛЕШ ОТКЛЮЧЕНА ПОЛНОСТЬЮ ---
    # Этот репозиторий предназначен ровно для одного сценария: запуск образа ИЗ ОЗУ, при
    # котором флеш не изменяется вообще. Команды записи (FLW, TFTP+AUTOBURN) в этой версии
    # заблокированы здесь, в единственной точке, через которую проходят оба пути записи.
    # Так исключён самый опасный класс ошибки: запись неподходящего образа во флеш
    # необратимо ломает загрузчик и превращает роутер в кирпич, который оживит только
    # программатор.
    raise SafetyError(
        "запись во флеш отключена в этой сборке инструментов. "
        "Публичная версия предназначена только для запуска образа из ОЗУ (ram_boot.py), "
        "при котором содержимое флеша не изменяется.")

    end = addr + length
    if end > FLASH_SIZE:
        raise SafetyError("запись 0x%X..0x%X выходит за пределы флеша (16 МБ)" % (addr, end))
    for lo, hi in allowed_ranges:
        if addr >= lo and end - 1 <= hi:
            return
    raise SafetyError(
        "запись 0x%X..0x%X ЗА ПРЕДЕЛАМИ разрешённого диапазона (%s) — отклонено "
        "ДО отправки в порт/передачи." %
        (addr, end - 1, ["0x%X-0x%X" % r for r in allowed_ranges]))


# --- разбор вывода DW/DB — вынесено в свободные функции, чтобы проверять их
# синтетическими данными без реального железа (формат подтверждён дизассемблером:
# DW -> "%08X:\t%08X\t%08X\t%08X\t%08X\n", DB -> "%08X: %02x %02x ..." до 16/строку)

_DW_LINE = re.compile(
    r"([0-9A-Fa-f]{8}):\s+([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})\s+"
    r"([0-9A-Fa-f]{8})\s+([0-9A-Fa-f]{8})")
# БЫЛО: r"^(...)" с re.MULTILINE — ломалось на живом железе (2026-08-11, Фаза 4,
# Этап A): каждая строка адреса в реальном выводе DB предваряется ЛИШНИМ `\r`
# (`...00\n\r\rA0A00010: ...`, не просто `\n`), поэтому `^`-привязка после `\n`
# указывала на этот `\r`, а не на первую hex-цифру, и regex не совпадал вообще
# — DB возвращал b"" молча (не исключение), что могло дать ЛОЖНО-успешную
# сверку в write_flash() (b"" == data[:0] проходит). Исправлено по образцу
# DW-регулярки выше: ищем паттерн где угодно в тексте, без привязки к началу
# строки — 8 hex-цифр сразу перед `:` встречаются только в реальных строках
# адреса, ложных совпадений в остальном выводе консоли не было и не ожидается.
_DB_LINE = re.compile(r"([0-9A-Fa-f]{8}):\s+((?:[0-9A-Fa-f]{2}\s+){1,16})")


def parse_dw_output(text, nwords):
    out = bytearray()
    for m in _DW_LINE.finditer(text):
        for g in m.groups()[1:]:
            out += bytes.fromhex(g)[::-1]  # слово в выводе — текст BE, в памяти лежит LE
    return bytes(out[:nwords * 4])


def parse_dw_output_strict(text, ram_addr, nwords):
    """Как `parse_dw_output`, но дополнительно проверяет, что адреса распознанных строк
    образуют СТРОГУЮ последовательность `ram_addr, ram_addr+16, ram_addr+32, ...` — без
    пропусков, повторов и перестановок.

    ЗАЧЕМ (найдено 2026-08-11, реальный инцидент чтения `mtd2`): повреждение при передаче
    по UART может заменить строку на ДОСЛОВНЫЙ ПОВТОР соседней строки (наблюдалось: одна и
    та же 62-байтная последовательность повторилась 7 раз подряд) — итоговое количество
    строк и суммарная длина при этом остаются верными, поэтому ни проверка длины чанка
    (`read_flash`, введена по итогам того же инцидента), ни сам `parse_dw_output` (который
    просто конкатенирует слова в порядке появления в тексте, не глядя на печатаемый
    адрес) такое не ловят — итоговые байты оказываются на месте неверными, а не отсутствующими.
    Здесь же адрес каждой строки — часть её собственного текста (`AXXXXXXX:`), поэтому
    достаточно сверить фактическую последовательность адресов с ожидаемой геометрией
    запроса, без дополнительного контроля чётности/CRC на стороне устройства."""
    nlines = (nwords + 3) // 4
    matches = list(_DW_LINE.finditer(text))
    addrs = [int(m.group(1), 16) for m in matches]
    expected = [ram_addr + 16 * i for i in range(nlines)]
    if addrs != expected:
        for i, (a, e) in enumerate(zip(addrs, expected)):
            if a != e:
                raise ValueError(
                    "строка %d: адрес 0x%X != ожидаемого 0x%X (распознано строк: %d, "
                    "ожидалось: %d)" % (i, a, e, len(addrs), nlines))
        raise ValueError("количество распознанных строк %d != ожидаемого %d"
                          % (len(addrs), nlines))
    out = bytearray()
    for m in matches:
        for g in m.groups()[1:]:
            out += bytes.fromhex(g)[::-1]
    return bytes(out[:nwords * 4])


def parse_db_output(text, nbytes):
    out = bytearray()
    for m in _DB_LINE.finditer(text):
        out += bytes.fromhex(m.group(2).replace(" ", ""))
    return bytes(out[:nbytes])


class RomLoader:
    def __init__(self, port=PORT_DEFAULT, baud=BAUD_DEFAULT, timeout=1.0,
                 allowed_write_ranges=None, logfile=None):
        if serial is None:
            raise SystemExit("нужен pyserial: pip install pyserial")
        self.allowed_write_ranges = allowed_write_ranges or list(DEFAULT_ALLOWED_WRITE_RANGES)
        os.makedirs(LOGDIR, exist_ok=True)
        if logfile is None:
            logfile = os.path.join(LOGDIR, "session-%s.log" % time.strftime("%Y%m%d-%H%M%S"))
        self.logfile = logfile
        self._log = open(logfile, "a", encoding="utf-8")
        self._log_line("=== подключение открыто, port=%s baud=%d ===" % (port, baud))
        self._log_line("разрешённые диапазоны записи: %s"
                       % ["0x%X-0x%X" % r for r in self.allowed_write_ranges])
        self.ser = serial.Serial(port, baud, timeout=timeout)

    def close(self):
        self._log_line("=== подключение закрыто ===")
        self._log.close()
        self.ser.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- низкоуровневый обмен -------------------------------------------

    def _log_line(self, msg):
        line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
        self._log.write(line + "\n")
        self._log.flush()

    def _check_forbidden(self, cmd):
        if re.search(r"erasechip", cmd, re.IGNORECASE):
            raise SafetyError(
                "команда %r содержит ERASECHIP — отправка заблокирована на уровне "
                "драйвера (стирает весь чип). Если это ДЕЙСТВИТЕЛЬНО нужно, редактировать "
                "нужно сам rtk_romloader.py, а не подавать это аргументом." % cmd)

    def read_quiet(self, quiet_ms=250, max_wait_s=8.0):
        """Читает из порта, пока не наступит пауза quiet_ms без новых байт
        (или не истечёт max_wait_s). Возвращает накопленные байты."""
        buf = b""
        deadline = time.time() + max_wait_s
        last_data = time.time()
        while time.time() < deadline:
            chunk = self.ser.read(4096)
            if chunk:
                buf += chunk
                last_data = time.time()
            else:
                if buf and (time.time() - last_data) * 1000 >= quiet_ms:
                    break
                time.sleep(0.02)
        return buf

    def send_raw(self, cmd, quiet_ms=250, max_wait_s=8.0):
        """Отправить команду голым \\r, дождаться тишины на линии, вернуть
        декодированный (latin-1, чтобы не падать на мусорных байтах) ответ."""
        self._check_forbidden(cmd)
        self._log_line(">> %s" % cmd)
        self.ser.reset_input_buffer()
        self.ser.write(cmd.encode("ascii") + b"\r")
        raw = self.read_quiet(quiet_ms=quiet_ms, max_wait_s=max_wait_s)
        text = raw.decode("latin-1")
        self._log_line("<< %r" % text)
        return text

    def confirm_yes(self):
        """Отправить 'Y' в ответ на приглашение (Y)es/(N)o."""
        self._log_line(">> Y (confirm)")
        self.ser.write(b"Y\r")
        raw = self.read_quiet(quiet_ms=250, max_wait_s=15.0)
        text = raw.decode("latin-1")
        self._log_line("<< %r" % text)
        return text

    def confirm_no(self):
        """Отправить 'N' — отклонить приглашение (Y)es/(N)o. Безопасный способ
        снять ЛЮБОЕ зависшее подтверждение (FLR/FLW), если предыдущая команда
        оборвалась (например, скрипт упал), не дожидаясь ответа Y/N — команда
        отклоняется, ничего не читается и не пишется."""
        self._log_line(">> N (decline)")
        self.ser.write(b"N\r")
        raw = self.read_quiet(quiet_ms=250, max_wait_s=15.0)
        text = raw.decode("latin-1")
        self._log_line("<< %r" % text)
        return text

    # --- команды без риска -----------------------------------------------

    def wait_prompt(self, max_wait_s=15.0):
        """Дождаться баннера/приглашения после включения питания+WPS. Возвращает
        весь накопленный вывод."""
        self._log_line("(ожидание приглашения <RealTek> после ручной перезагрузки с WPS)")
        raw = self.read_quiet(quiet_ms=500, max_wait_s=max_wait_s)
        text = raw.decode("latin-1")
        self._log_line("<< %r" % text)
        return text

    def cmd_fli(self):
        """FLI — инициализация/опрос флеша. Ожидаемый ответ содержит
        'w25q128, size=16MB'."""
        return self.send_raw("FLI")

    def cmd_ipconfig(self, ip=None):
        """IPCONFIG [a.b.c.d] — без аргумента печатает текущий адрес устройства.

        ВАЖНО (найдено офлайн-разбором токенайзера, 2026-08-11): разделитель
        аргументов консоли — ПРОБЕЛ (0x8000A754), не двоеточие. Первая версия
        этого метода слала "IPCONFIG:<ip>" — это один нераспознанный токен,
        консоль отвечает "Unknown command !". Баг не проявился в Фазе 3, т.к.
        эта команда тогда не вызывалась. См. bootloader-analysis.md, раздел
        «Сеть и TFTP»."""
        return self.send_raw("IPCONFIG %s" % ip if ip else "IPCONFIG")

    def cmd_loadaddr(self, addr=None):
        """LOADADDR [hex] — без аргумента печатает текущий адрес приёма TFTP
        (по умолчанию 0xA0A00000). Тот же баг разделителя, что и у IPCONFIG —
        исправлено на пробел."""
        return self.send_raw("LOADADDR 0x%X" % addr if addr is not None else "LOADADDR")

    def cmd_autoburn(self, enabled):
        return self.send_raw("AUTOBURN %d" % (1 if enabled else 0))

    def cmd_eth(self, wait_s=5.0):
        """ETH — поднять Ethernet и сетевой стек загрузчика. ОБЯЗАТЕЛЬНА перед
        любым TFTP: флаг готовности сети (0x800148E4) взводится ТОЛЬКО внутри
        обработчика этой команды (офлайн-разбор 2026-08-11) — без неё оба
        обработчика TFTP-пакетов (WRQ/DATA) молча ничего не делают. ETH также
        безусловно перезаписывает IP/MAC на дефолтные (192.168.1.6) — вызывать
        СТРОГО до IPCONFIG, не после. Ожидаемый ответ содержит
        '---Ethernet init Okay V003---'."""
        text = self.send_raw("ETH", quiet_ms=250, max_wait_s=wait_s)
        if "Ethernet init Okay" not in text:
            raise RuntimeError("ETH не подтвердил инициализацию, ответ: %r" % text)
        return text

    # --- DW/DB — разбор вывода ---------------------------------------------

    def cmd_dw(self, addr, nwords):
        """DW <addr> <len> — читает nwords 32-битных слов из RAM, возвращает bytes
        (little-endian, как лежат в памяти MIPS LE).

        ВАЖНО: адрес парсится загрузчиком как hex, а длина — КАК DECIMAL
        (strtoul(..., 10)), в отличие от всех остальных команд (FLR/FLW/EB —
        везде hex). Подтверждено дизассемблированием обработчика DW
        (0x8000CFD8) и живым тестом: `DW addr 0x40` вернул пустой вывод
        (strtoul("0x40",10) останавливается на символе 'x', давая 0), тогда
        как `DW addr 64` работает. Длина в словах (4 байта), одна строка
        вывода = 4 слова = 16 байт."""
        text = self.send_raw("DW 0x%X %d" % (addr, nwords))
        return parse_dw_output(text, nwords)

    def cmd_db(self, addr, nbytes):
        """DB <addr> <len> — читает nbytes байт из RAM построчно (до 16 в строке).
        Та же особенность, что и у DW: адрес — hex, длина — decimal."""
        text = self.send_raw("DB 0x%X %d" % (addr, nbytes))
        return parse_db_output(text, nbytes)

    def cmd_eb(self, addr, data, chunk=16):
        """EB <addr> <v1> <v2> ... — пишет данные в RAM небольшими кусками (по
        умолчанию 16 байт за вызов, безопасный запас относительно неизвестного
        лимита аргументов интерпретатора)."""
        for off in range(0, len(data), chunk):
            piece = data[off:off + chunk]
            args = " ".join("0x%02X" % b for b in piece)
            self.send_raw("EB 0x%X %s" % (addr + off, args))

    # --- чтение флеша (FLR + DW) ------------------------------------------

    def read_flash(self, flash_addr, length, ram_scratch=0xA0400000, chunk=0x1000,
                    max_retries=3):
        """Читает length байт с флеша через FLR (flash->RAM) + DW (RAM->текст).
        RAM-адрес по умолчанию выбран далеко от TFTP load area (0xA0A00000) и
        от значимых структур загрузчика.

        ВАЖНО (найдено 2026-08-11 на живом чтении mtd2, 4МБ, два независимых бага):
        1. `parse_dw_output` молча возвращает МЕНЬШЕ байт, чем запрошено, если хотя бы
           одна строка текстового hex-дампа пропала при передаче по UART -- БЕЗ
           исключения. Без проверки длины на каждый чанк итоговый файл получался короче
           запрошенного и, что хуже, все данные ПОСЛЕ места пропуска сдвинуты
           относительно настоящих адресов флеша -- непригодно для выбора адреса записи.
        2. Проверки одной только длины НЕДОСТАТОЧНО: повреждение может заменить строку
           на дословный повтор соседней (реальный случай -- одна и та же 62-байтная
           последовательность повторилась 7 раз подряд), что сохраняет и число строк, и
           суммарную длину, но даёт неверные байты НЕ там, где нужно. Поэтому здесь
           используется `parse_dw_output_strict` -- сверяет ещё и последовательность
           адресов, напечатанных самим устройством в каждой строке.
        Оба случая перечитывают чанк заново (до max_retries раз), прежде чем перейти
        к следующему."""
        out = bytearray()
        remaining = length
        addr = flash_addr
        while remaining > 0:
            n = min(chunk, remaining)
            nwords = (n + 3) // 4
            data = None
            last_err = None
            for attempt in range(1, max_retries + 1):
                text = self.send_raw("FLR 0x%X 0x%X 0x%X" % (ram_scratch, addr, n))
                if "(Y)es" not in text and "(Y)" not in text:
                    raise RuntimeError("FLR не запросил подтверждение, ответ: %r" % text)
                conf = self.confirm_yes()
                if "Successed" not in conf and "Success" not in conf:
                    raise RuntimeError("FLR не подтвердил успех, ответ: %r" % conf)
                dw_text = self.send_raw("DW 0x%X %d" % (ram_scratch, nwords))
                try:
                    chunk_data = parse_dw_output_strict(dw_text, ram_scratch, nwords)
                except ValueError as exc:
                    last_err = str(exc)
                    print("!!! чанк 0x%X: нарушена последовательность адресов DW (%s) "
                          "(попытка %d/%d), перечитываю..." % (addr, last_err, attempt, max_retries))
                    continue
                if len(chunk_data) == n:
                    data = chunk_data
                    break
                last_err = "получено %d/%d байт" % (len(chunk_data), n)
                print("!!! чанк 0x%X: %s (попытка %d/%d), перечитываю..."
                      % (addr, last_err, attempt, max_retries))
            if data is None:
                raise RuntimeError(
                    "чанк по адресу 0x%X: не удалось получить полные %d байт за %d попыток "
                    "(последняя ошибка: %s)" % (addr, n, max_retries, last_err))
            out += data
            addr += n
            remaining -= n
        assert len(out) == length, "внутренняя ошибка: итоговая длина %d != %d" % (len(out), length)
        return bytes(out)

    # --- запись флеша (EB + FLW) — с предохранителями -----------------------

    def _check_write_range(self, addr, length):
        check_range_allowed(addr, length, self.allowed_write_ranges)

    def cmd_flw(self, flash_addr, ram_addr, length, spi_cnt=1):
        """FLW <flash_off> <ram_src> <len> <spi_cnt> — RAM -> флеш.
        `spi_cnt` в реальности не читается загрузчиком (см. bootloader-analysis.md),
        но передаётся ради читаемости лога/совместимости со справкой команды.

        ВАЖНО (найдено на живом тесте 2026-08-10): интерактивная команда `FLW`
        НЕ печатает "Flash Write Successed!"/"Failed" — эти строки принадлежат
        ТОЛЬКО автоматической функции `burn_image` (TFTP+AUTOBURN), не самому
        обработчику FLW (подтверждено дизассемблированием: в `0x8000D930` после
        вызова `flash_write` нет ни одного printf с этими строками). Единственный
        надёжный способ убедиться в успехе — читать записанное обратно (см.
        `write_flash()`), а не парсить текст ответа на подтверждение."""
        self._check_write_range(flash_addr, length)
        text = self.send_raw("FLW 0x%X 0x%X 0x%X %d" % (flash_addr, ram_addr, length, spi_cnt))
        if "(Y)es" not in text:
            raise RuntimeError("FLW не запросил подтверждение, ответ: %r" % text)
        conf = self.confirm_yes()
        if "Abort" in conf:
            raise RuntimeError("FLW отменён загрузчиком (Abort!): %r" % conf)
        return conf

    def write_flash(self, flash_addr, data, ram_scratch=0xA0400000, yes=False,
                    confirm_cb=None):
        """Полный цикл: EB (в RAM) -> FLW (RAM -> флеш) -> FLR+DB (обратное чтение
        для верификации). Диапазон проверяется ДО первой отправки в порт.
        Единственный источник истины об успехе — совпадение прочитанных обратно
        байт с тем, что писали (см. cmd_flw)."""
        self._check_write_range(flash_addr, len(data))
        summary = ("ЗАПИСЬ: %d байт в флеш по адресу 0x%08X..0x%08X (через RAM 0x%08X)"
                  % (len(data), flash_addr, flash_addr + len(data) - 1, ram_scratch))
        print(summary)
        self._log_line(summary)
        if not yes:
            if confirm_cb is not None:
                if not confirm_cb(summary):
                    print("отменено пользователем")
                    return False
            else:
                ans = input("Подтвердить запись? (yes/no): ").strip().lower()
                if ans not in ("yes", "y"):
                    print("отменено пользователем")
                    return False
        self.cmd_eb(ram_scratch, data)
        readback = self.cmd_db(ram_scratch, min(len(data), 256))
        if readback != data[:len(readback)]:
            raise RuntimeError(
                "данные в RAM после EB не совпадают с ожидаемыми — не продолжаю с FLW. "
                "Хочу=%s получил=%s" % (data[:16].hex(), readback[:16].hex()))
        self.cmd_flw(flash_addr, ram_scratch, len(data))
        flash_readback = self.read_flash(flash_addr, len(data), ram_scratch=ram_scratch)
        if flash_readback != data:
            raise RuntimeError(
                "ПРОВЕРКА ПОСЛЕ FLW НЕ ПРОШЛА — во флеше не то, что писали. "
                "Хочу=%s получил=%s" % (data[:16].hex(), flash_readback[:16].hex()))
        return True

    # --- заливка через TFTP+AUTOBURN (Фаза 4) -------------------------------

    def _neutralize_wrt_hack(self, loadaddr, total_file_len):
        """Обнулить 4 байта сразу за ожидаемым концом принятого файла в RAM —
        предохранитель от 'wrt image' hack в `burn_image`: если длина секции
        кратна `0x1000` И сразу за телом лежат байты `DE AD C0 DE`, загрузчик
        молча добавляет 4 байта к длине записи (bootloader-analysis.md,
        раздел «Сеть и TFTP»). Мусор от предыдущих операций в этой области
        RAM иначе может случайно содержать эту сигнатуру."""
        addr = loadaddr + total_file_len
        self.cmd_eb(addr, b"\x00\x00\x00\x00")

    def send_image_via_tftp(self, image_bytes, remote_name, autoburn, host=None,
                            loadaddr=0xA0A00000, do_eth=True, tftp_kwargs=None,
                            uart_timeout_s=120.0):
        """Полный цикл Фазы 4: `ETH` -> `LOADADDR` -> `AUTOBURN` -> нейтрализация
        wrt-hack -> TFTP-заливка (в отдельном потоке) -> чтение/лог UART в
        основном потоке, пока идёт передача и (если `autoburn`) сама запись.

        `image_bytes` — уже собранный `rtk_mkimg.py` образ (заголовок+тело).
        Диапазон `burnAddr..burnAddr+len` проверяется ДО передачи против
        `self.allowed_write_ranges` — сам загрузчик область записи вообще не
        проверяет (см. bootloader-analysis.md) — это единственная защита для
        пути TFTP+AUTOBURN, аналог белого списка у `write_flash()`/`cmd_flw()`.

        Возвращает `(uart_text, tftp_stats)`. Бросает исключение, если TFTP-
        передача не удалась (детали — в логе `rtk_tftp_put`, путь в
        `stats['logfile']`, доступен и при ошибке через `result`)."""
        hdr = rtk_mkimg.unpack_header(image_bytes)
        if len(image_bytes) < 16 + hdr["length"]:
            raise ValueError("image_bytes короче, чем заявлено в заголовке (%d нужно, %d есть)"
                             % (16 + hdr["length"], len(image_bytes)))
        try:
            check_range_allowed(hdr["burn_addr"], hdr["length"], self.allowed_write_ranges)
        except SafetyError as e:
            raise SafetyError(
                "образ %r: %s (AUTOBURN запишет туда БЕЗ проверки со стороны "
                "загрузчика — это отклонено драйвером ДО передачи)" % (remote_name, e))

        summary = ("TFTP: %r (%d байт, sig=%s, burnAddr=0x%X, len=0x%X), AUTOBURN=%d"
                  % (remote_name, len(image_bytes), hdr["sig"], hdr["burn_addr"], hdr["length"], int(autoburn)))
        print(summary)
        self._log_line(summary)

        if do_eth:
            self.cmd_eth()
        self.cmd_loadaddr(loadaddr)
        self.cmd_autoburn(autoburn)
        self._neutralize_wrt_hack(loadaddr, len(image_bytes))

        tftp_kwargs = dict(tftp_kwargs or {})
        tftp_kwargs.setdefault("host", host or rtk_tftp_put.DEFAULT_HOST)
        result = {}

        def _run_tftp():
            try:
                result["stats"] = rtk_tftp_put.put(image_bytes, remote_name=remote_name, **tftp_kwargs)
            except Exception as e:
                result["error"] = e

        th = threading.Thread(target=_run_tftp, name="tftp-put", daemon=True)
        th.start()

        # Читаем UART, пока поток передачи жив (сама TFTP-передача — секунды),
        # а ПОСЛЕ его завершения — до settle_quiet_s НЕПРЕРЫВНОЙ тишины на линии
        # или до overall_deadline, что раньше. НЕ фиксированный короткий хвост:
        # последний ACK шлётся ДО burn_image (bootloader-analysis.md), поэтому
        # поток TFTP завершается почти сразу, а реальная запись/стирание на
        # роутере для многосекторных образов может идти ещё много секунд
        # (найдено 2026-08-11 на живом Этапе B1: 522КБ/~128 секторов — фиксированные
        # 3с хвоста НЕ хватило, readback ушёл в FLR посреди печати прогресса точками
        # и получил мусор вместо ответа; данные при этом не пострадали — FLR
        # безопасно отказался, а не подставил ложный результат). Прогресс-точки
        # печатаются с паузами МЕЖДУ ними — settle_quiet_s должен быть заведомо
        # больше типичной паузы между двумя точками, иначе again оборвём рано.
        uart_chunks = []
        overall_deadline = time.time() + uart_timeout_s
        settle_quiet_s = 5.0
        last_activity = time.time()
        while True:
            chunk = self.read_quiet(quiet_ms=300, max_wait_s=1.0)
            now = time.time()
            if chunk:
                uart_chunks.append(chunk)
                last_activity = now
            if not th.is_alive() and (now - last_activity) >= settle_quiet_s:
                break
            if now > overall_deadline:
                self._log_line(
                    "!!! uart_timeout_s (%.0fs) истёк (поток TFTP %s) — не дождались "
                    "%.0fс тишины после последней активности на линии" %
                    (uart_timeout_s, "жив" if th.is_alive() else "завершён", settle_quiet_s))
                break
        th.join(timeout=5.0)

        uart_text = b"".join(uart_chunks).decode("latin-1")
        self._log_line("<< (UART во время TFTP) %r" % uart_text)

        if "error" in result:
            raise result["error"]
        return uart_text, result.get("stats")


# --- CLI --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default=PORT_DEFAULT)
    ap.add_argument("--baud", type=int, default=BAUD_DEFAULT)
    ap.add_argument("--allow", action="append", default=None,
                    help="доп. разрешённый диапазон записи 'LO-HI' (hex, включительно), можно "
                         "повторять; ДОБАВЛЯЕТСЯ к DEFAULT_ALLOWED_WRITE_RANGES, не заменяет его. "
                         "Пример: --allow 0xEC0000-0xEC0FFF")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("wait", help="дождаться приглашения после ручной перезагрузки+WPS")
    p.add_argument("--timeout", type=float, default=15.0, help="секунд ожидания (по умолчанию 15)")
    sub.add_parser("info", help="FLI — опросить флеш")
    sub.add_parser("abort", help="отправить 'N' — снять любое зависшее подтверждение (Y)es/(N)o")

    p = sub.add_parser("read", help="прочитать участок флеша (FLR+DW)")
    p.add_argument("addr", help="hex, напр. 0x00B00000")
    p.add_argument("length", help="hex или dec, байт")
    p.add_argument("--out", required=True)

    p = sub.add_parser("write", help="записать участок флеша (EB+FLW), с предохранителями")
    p.add_argument("addr", help="hex, напр. 0x00B00000")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--file", help="файл с данными для записи")
    g.add_argument("--pattern", help="hex-строка (напр. 001122...) для быстрого теста")
    p.add_argument("--yes", action="store_true", help="не спрашивать подтверждение")

    p = sub.add_parser("verify", help="прочитать участок и сравнить с файлом")
    p.add_argument("addr")
    p.add_argument("--file", required=True)

    sub.add_parser("eth", help="ETH — поднять сеть загрузчика (ОБЯЗАТЕЛЬНО перед TFTP)")

    p = sub.add_parser("ipconfig", help="IPCONFIG — показать/задать IP устройства (вызывать после eth)")
    p.add_argument("ip", nargs="?", default=None, help="a.b.c.d; без аргумента — показать текущий")

    p = sub.add_parser("loadaddr", help="LOADADDR — показать/задать адрес приёма TFTP")
    p.add_argument("addr", nargs="?", default=None, help="hex; без аргумента — показать текущий")

    p = sub.add_parser("autoburn", help="AUTOBURN 0|1 — вкл/выкл автозапись принятого по TFTP")
    p.add_argument("enabled", type=int, choices=[0, 1])

    p = sub.add_parser("dumpram", help="DB/DW — прочитать RAM НАПРЯМУЮ (не через FLR, в отличие от read)")
    p.add_argument("addr", help="hex, напр. 0xA0A00000")
    p.add_argument("length", type=int, help="decimal байт (DB) — см. bootloader-analysis.md про decimal-длину")
    p.add_argument("--out", default=None, help="сохранить сырые байты в файл (опционально)")

    p = sub.add_parser("tftp", help="залить образ по TFTP (ETH+LOADADDR+AUTOBURN+передача), Фаза 4")
    p.add_argument("image", help="файл образа, собранный rtk_mkimg.py build")
    p.add_argument("--name", default=None, help="имя файла для TFTP (по умолчанию — basename образа)")
    p.add_argument("--autoburn", type=int, choices=[0, 1], default=0,
                   help="0 — сухой прогон, только принять в RAM (по умолчанию); "
                        "1 — реально записать во флеш")
    p.add_argument("--host", default=None, help="IP консоли загрузчика (по умолчанию — 192.168.1.6)")
    p.add_argument("--loadaddr", default="0xA0A00000", help="адрес приёма TFTP, hex")
    p.add_argument("--skip-eth", action="store_true",
                    help="не выполнять ETH перед передачей (если уже выполнен в этом же подключении)")
    p.add_argument("--verify", action="store_true",
                    help="после --autoburn 1 прочитать записанное обратно и сверить с образом")
    p.add_argument("--uart-timeout", type=float, default=120.0,
                    help="сек ожидания UART после конца передачи (по умолчанию 120)")

    args = ap.parse_args()

    def _int(s):
        return int(s, 0)

    allowed_ranges = list(DEFAULT_ALLOWED_WRITE_RANGES)
    if args.allow:
        for spec in args.allow:
            lo_s, hi_s = spec.split("-")
            allowed_ranges.append((_int(lo_s), _int(hi_s)))

    with RomLoader(port=args.port, baud=args.baud, allowed_write_ranges=allowed_ranges) as rl:
        print("лог подключения: %s" % rl.logfile)

        if args.cmd == "wait":
            print(rl.wait_prompt(max_wait_s=args.timeout))

        elif args.cmd == "info":
            print(rl.cmd_fli())

        elif args.cmd == "abort":
            print(rl.confirm_no())

        elif args.cmd == "read":
            addr = _int(args.addr)
            length = _int(args.length)
            data = rl.read_flash(addr, length)
            with open(args.out, "wb") as f:
                f.write(data)
            print("прочитано %d байт с 0x%08X -> %s" % (len(data), addr, args.out))

        elif args.cmd == "write":
            addr = _int(args.addr)
            if args.file:
                with open(args.file, "rb") as f:
                    data = f.read()
            else:
                data = bytes.fromhex(args.pattern)
            ok = rl.write_flash(addr, data, yes=args.yes)
            sys.exit(0 if ok else 1)

        elif args.cmd == "verify":
            addr = _int(args.addr)
            with open(args.file, "rb") as f:
                expected = f.read()
            actual = rl.read_flash(addr, len(expected))
            if actual == expected:
                print("СОВПАДАЕТ: %d байт по 0x%08X идентичны файлу" % (len(expected), addr))
            else:
                ndiff = sum(1 for a, b in zip(actual, expected) if a != b)
                print("РАСХОЖДЕНИЕ: %d из %d байт отличаются" % (ndiff, len(expected)))
                sys.exit(1)

        elif args.cmd == "eth":
            print(rl.cmd_eth())

        elif args.cmd == "ipconfig":
            print(rl.cmd_ipconfig(args.ip))

        elif args.cmd == "loadaddr":
            addr = _int(args.addr) if args.addr is not None else None
            print(rl.cmd_loadaddr(addr))

        elif args.cmd == "autoburn":
            print(rl.cmd_autoburn(bool(args.enabled)))

        elif args.cmd == "dumpram":
            addr = _int(args.addr)
            data = rl.cmd_db(addr, args.length)
            print("0x%08X: %s" % (addr, data.hex()))
            if args.out:
                with open(args.out, "wb") as f:
                    f.write(data)
                print("-> %s (%d байт)" % (args.out, len(data)))

        elif args.cmd == "tftp":
            with open(args.image, "rb") as f:
                image_bytes = f.read()
            remote_name = args.name or os.path.basename(args.image)
            loadaddr = _int(args.loadaddr)
            uart_text, stats = rl.send_image_via_tftp(
                image_bytes, remote_name, autoburn=bool(args.autoburn),
                host=args.host, loadaddr=loadaddr, do_eth=not args.skip_eth,
                uart_timeout_s=args.uart_timeout)
            print("--- UART во время передачи/записи ---")
            print(uart_text)
            if stats:
                print("--- TFTP статистика ---")
                print("bytes=%(bytes)d seconds=%(seconds).2f kbps=%(kbps).1f "
                      "server_tid=%(server_tid)s retransmits=%(retransmits)d" % stats)
                print("лог TFTP: %s" % stats["logfile"])
            if args.autoburn and args.verify:
                hdr = rtk_mkimg.unpack_header(image_bytes)
                body = image_bytes[16:16 + hdr["length"]]
                print("--- readback-верификация 0x%X, %d байт ---" % (hdr["burn_addr"], len(body)))
                actual = rl.read_flash(hdr["burn_addr"], len(body))
                if actual == body:
                    print("СОВПАДАЕТ: записанные %d байт по 0x%08X идентичны образу"
                          % (len(body), hdr["burn_addr"]))
                else:
                    ndiff = sum(1 for a, b in zip(actual, body) if a != b)
                    print("РАСХОЖДЕНИЕ: %d из %d байт отличаются" % (ndiff, len(body)))
                    sys.exit(1)


if __name__ == "__main__":
    main()
