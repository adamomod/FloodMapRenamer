import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from renamer import Row, build_names, candidates, detect_tma, export_zip, normalize_tma


class TestRenamer(unittest.TestCase):
    def test_names_and_collision(self):
        rows = [Row("a.jpeg", "3015", "", "OK"), Row("folder/b.jpg", "3090", "", "OK")]
        self.assertEqual(build_names(rows, "Grogol", "1", "Hulu", "Terrain")[0], "Grogol_Zona1_Hulu_R3015.jpg")
        self.assertEqual(build_names(rows, "Grogol", "Zona1", "Hulu", "Satellite")[1], "Grogol_Zona1_Hulu_S3090.jpg")
        rows[1].tma = "3015"
        with self.assertRaisesRegex(ValueError, "ganda"):
            build_names(rows, "Grogol", "1", "Hulu", "Terrain")

    def test_tma_format_and_label(self):
        self.assertEqual(normalize_tma("3.015"), "3015")
        self.assertGreater(max(score for score, value in candidates("TMA: 3015\nRW: 01") if value == "3015"), 100)
        with self.assertRaises(ValueError):
            normalize_tma("30/15")

    def test_ocr_and_export(self):
        im = Image.new("RGB", (1200, 650), "white")
        draw = ImageDraw.Draw(im)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
        draw.text((810, 65), "TMA: 3015", fill="black", font=font)
        tma, raw, status = detect_tma(im)
        self.assertEqual(tma, "3015", raw)
        self.assertEqual(status, "OK", raw)
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "src.zip", Path(directory) / "out.zip"
            data = io.BytesIO()
            im.save(data, format="JPEG")
            with zipfile.ZipFile(source, "w") as z:
                z.writestr("nested/a.jpeg", data.getvalue())
            row = Row("nested/a.jpeg", tma, raw, status)
            export_zip(str(source), str(target), [row], build_names([row], "Grogol", "1", "Hulu", "Terrain"))
            with zipfile.ZipFile(target) as z:
                self.assertEqual(sorted(z.namelist()), ["Grogol_Zona1_Hulu_R3015.jpg", "laporan_rename.csv"])


if __name__ == "__main__":
    unittest.main()
