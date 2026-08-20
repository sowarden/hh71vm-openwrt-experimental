import hashlib
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE = ROOT / "firmware"
RAM_IMAGE = FIRMWARE / "openwrt-rtkmipsel-rtl8197f-hh71vm-nfjrom.bin"
RAM_IMAGE_SHA256 = "4d4a329edbe034e431a12f4f57aa8c46c4f4fe51a4d1d161a852b6a9134691f7"
CYRILLIC_UTF8 = re.compile(rb"(?:\xd0[\x80-\xbf]|\xd1[\x80-\xbf])")


class PublicationBoundaryTests(unittest.TestCase):
    def test_published_ram_image_hash(self):
        digest = hashlib.sha256(RAM_IMAGE.read_bytes()).hexdigest()
        self.assertEqual(digest, RAM_IMAGE_SHA256)

    def test_no_prebuilt_flash_image_is_published(self):
        forbidden = ("fwupg", "sysupgrade", "factory", "flash")
        offenders = [
            path.name
            for path in FIRMWARE.iterdir()
            if path.is_file() and any(marker in path.name.lower() for marker in forbidden)
        ]
        self.assertEqual(offenders, [])

    def test_public_text_is_english_only(self):
        offenders = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            if ".git" in relative.parts or "__pycache__" in relative.parts:
                continue
            if path.suffix.lower() in {
                ".bin",
                ".gif",
                ".jpeg",
                ".jpg",
                ".png",
                ".pyc",
                ".webp",
            }:
                continue
            if any(part.endswith("-logs") for part in relative.parts):
                continue
            if relative.as_posix().endswith("/usr/sbin/iwpriv"):
                continue
            if CYRILLIC_UTF8.search(path.read_bytes()):
                offenders.append(relative.as_posix())
        self.assertEqual(offenders, [])

    def test_issue_forms_keep_required_reporting_fields(self):
        template_dir = ROOT / ".github" / "ISSUE_TEMPLATE"
        compatibility = (template_dir / "01-compatibility-report.yml").read_text(
            encoding="utf-8"
        )
        bug = (template_dir / "02-bug-report.yml").read_text(encoding="utf-8")
        config = (template_dir / "config.yml").read_text(encoding="utf-8")

        for marker in (
            "id: outcome",
            "id: model",
            "id: board-revision",
            "id: stock-version",
            "id: image-sha256",
            "id: uart-log",
            "id: wifi-24",
            "id: wifi-5",
            "id: modem",
        ):
            self.assertIn(marker, compatibility)
        for marker in ("id: summary", "id: steps", "id: uart-log"):
            self.assertIn(marker, bug)
        self.assertIn("blank_issues_enabled: false", config)


if __name__ == "__main__":
    unittest.main()
