"""ZIP image inventory, OCR and safe export for flood map screenshots."""
from __future__ import annotations

import csv
import io
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

IMAGE_SUFFIXES = {".jpg", ".jpeg"}
MAX_IMAGES = 10000
MAX_IMAGE_BYTES = 40 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024


@dataclass
class Row:
    source: str
    tma: str
    raw: str
    status: str


def image_entries(path: str) -> list[zipfile.ZipInfo]:
    with zipfile.ZipFile(path) as archive:
        entries = [i for i in archive.infolist() if not i.is_dir() and
                   Path(i.filename).suffix.lower() in IMAGE_SUFFIXES]
        if not entries:
            raise ValueError("ZIP tidak berisi JPG/JPEG.")
        if len(entries) > MAX_IMAGES:
            raise ValueError(f"ZIP melebihi batas {MAX_IMAGES} gambar.")
        if any(i.file_size > MAX_IMAGE_BYTES for i in entries):
            raise ValueError("Ada gambar lebih besar dari 40 MB.")
        if sum(i.file_size for i in entries) > MAX_TOTAL_BYTES:
            raise ValueError("Total gambar dalam ZIP lebih besar dari 2 GB.")
        return entries


def _tesseract() -> tuple[str, dict[str, str]]:
    if getattr(sys, "frozen", False):
        root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        binary = root / "tesseract" / "tesseract.exe"
        data = root / "tesseract" / "tessdata"
        if not binary.is_file() or not (data / "eng.traineddata").is_file():
            raise RuntimeError("Mesin OCR tidak lengkap dalam aplikasi.")
        return str(binary), {**os.environ, "TESSDATA_PREFIX": str(data)}
    return os.environ.get("TESSERACT_CMD", "tesseract"), os.environ.copy()


def _ocr(picture: Image.Image, psm: int) -> str:
    binary, env = _tesseract()
    data = io.BytesIO()
    picture.save(data, format="PNG")
    try:
        completed = subprocess.run(
            [binary, "stdin", "stdout", "-l", "eng", "--psm", str(psm)],
            input=data.getvalue(), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env, timeout=25, check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Tesseract OCR tidak ditemukan atau terlalu lama merespons.") from exc
    if completed.returncode:
        raise RuntimeError("OCR gagal: " + completed.stderr.decode("utf-8", errors="replace")[:240])
    return completed.stdout.decode("utf-8", errors="replace")


def normalize_tma(value: str) -> str:
    """Retain digits; a single dot/comma is accepted as a display separator."""
    value = value.strip()
    if not re.fullmatch(r"\d+(?:[.,]\d+)?", value):
        raise ValueError("TMA harus berisi angka (opsional satu titik/koma).")
    digits = re.sub(r"\D", "", value)
    if not 1 <= len(digits) <= 8:
        raise ValueError("TMA harus berisi 1–8 digit.")
    return digits


def candidates(text: str) -> list[tuple[int, str]]:
    """Score numbers near TMA/WSE and R/S rather than blindly taking map labels."""
    clean = text.upper().replace("O", "0")
    found: list[tuple[int, str]] = []
    for m in re.finditer(r"(?<!\d)\d{1,6}(?:[.,]\d{1,4})?(?!\d)", clean):
        value = m.group()
        digits = re.sub(r"\D", "", value)
        if not 2 <= len(digits) <= 8:
            continue
        left = clean[max(0, m.start() - 35):m.start()]
        near = left[-17:]
        score = 0
        if re.search(r"T\s*M\s*A\s*[:=\- ]*\s*$", near):
            score += 100
        elif re.search(r"(?:WSE|WATER\s*LEVEL|MUKA\s*AIR)\s*[:=\- ]*\s*$", near):
            score += 80
        if re.search(r"(?:^|\W)[RS]\s*[:=\- ]*\s*$", near):
            score += 55
        if re.search(r"(?:ZONA|ZONE|RW|DATE|TAHUN)\s*[:=\- ]*\s*$", near):
            score -= 70
        score += min(len(digits), 4)
        found.append((score, digits))
    return found


def detect_tma(image: Image.Image) -> tuple[str, str, str]:
    image = ImageOps.exif_transpose(image).convert("RGB")
    w, h = image.size
    # Screenshot labels occur in the upper right; use two crop sizes.
    crops = [image.crop((int(w * x), 0, w, int(h * y))) for x, y in ((.58, .31), (.72, .19))]
    observations: list[tuple[int, str]] = []
    raw: list[str] = []
    for crop in crops:
        if crop.width < 40 or crop.height < 16:
            continue
        scale = min(3, max(1, 1200 / crop.width))
        gray = ImageOps.grayscale(crop)
        if scale > 1:
            gray = gray.resize((int(gray.width * scale), int(gray.height * scale)), Image.Resampling.LANCZOS)
        variants = [ImageEnhance.Contrast(gray).enhance(2), ImageOps.autocontrast(gray).point(lambda p: 255 if p > 145 else 0)]
        for variant in variants:
            for psm in (6, 11):
                result = _ocr(variant, psm).strip()
                if result:
                    raw.append(result.replace("\n", " ")[:160])
                    observations.extend(candidates(result))
    if not observations:
        return "", " | ".join(raw[:4]), "PERIKSA: TMA tidak ditemukan"
    totals: dict[str, int] = {}
    for score, digits in observations:
        totals[digits] = totals.get(digits, 0) + max(score, 1)
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    best, best_score = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0
    confident = best_score >= 105 and best_score >= 2 * runner
    status = "OK" if confident else "PERIKSA: pembacaan ambigu"
    return best, " | ".join(raw[:4]), status


def scan(path: str, progress=None) -> list[Row]:
    entries = image_entries(path)
    rows = []
    with zipfile.ZipFile(path) as archive:
        for index, info in enumerate(entries, 1):
            try:
                with archive.open(info) as source:
                    with Image.open(source) as image:
                        tma, raw, status = detect_tma(image)
            except RuntimeError:
                raise
            except Exception as exc:
                tma, raw, status = "", str(exc)[:160], "PERIKSA: gambar tidak terbaca"
            rows.append(Row(info.filename, tma, raw, status))
            if progress:
                progress(index, len(entries))
    return rows


def safe_part(part: str, label: str) -> str:
    part = part.strip().replace(" ", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", part):
        raise ValueError(f"{label} hanya boleh huruf, angka, _ dan -, tanpa spasi.")
    return part


def build_names(rows: list[Row], kali: str, zona: str, lokasi: str, basemap: str) -> list[str]:
    kali = safe_part(kali, "Nama Kali")
    zona = safe_part(zona, "Nomor Zona")
    lokasi = safe_part(lokasi, "Lokasi DAS")
    if not zona.lower().startswith("zona"):
        zona = "Zona" + zona
    letter = {"Terrain": "R", "Satellite": "S"}.get(basemap)
    if not letter:
        raise ValueError("Pilih Terrain atau Satellite.")
    names = []
    for row in rows:
        if row.status != "OK":
            raise ValueError(f"Periksa TMA untuk {row.source} sebelum ekspor.")
        names.append(f"{kali}_{zona}_{lokasi}_{letter}{normalize_tma(row.tma)}.jpg")
    if len({name.lower() for name in names}) != len(names):
        raise ValueError("Ada nilai TMA ganda. Nama hasil akan bertabrakan; koreksi atau pisahkan gambar dalam ZIP.")
    return names


def export_zip(source_zip: str, output_zip: str, rows: list[Row], names: list[str]) -> None:
    if len(rows) != len(names):
        raise ValueError("Jumlah gambar dan nama tidak cocok.")
    if Path(source_zip).resolve() == Path(output_zip).resolve():
        raise ValueError("Output tidak boleh menimpa ZIP masukan.")
    entries = image_entries(source_zip)
    if [entry.filename for entry in entries] != [row.source for row in rows]:
        raise ValueError("ZIP masukan berubah; baca ulang sebelum ekspor.")
    output = Path(output_zip)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".rename_", suffix=".zip", dir=output.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(source_zip) as src, zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            sheet = io.StringIO()
            writer = csv.writer(sheet)
            writer.writerow(["file_asal", "file_hasil", "tma", "status", "teks_ocr"])
            for info, row, name in zip(entries, rows, names):
                with src.open(info) as handle:
                    data = handle.read(MAX_IMAGE_BYTES + 1)
                if len(data) > MAX_IMAGE_BYTES:
                    raise ValueError("Gambar melebihi batas ukuran saat ekspor.")
                # Pillow re-encodes to ensure .jpg matches JPEG bytes, including input .jpeg.
                with Image.open(io.BytesIO(data)) as im:
                    im = ImageOps.exif_transpose(im).convert("RGB")
                    buf = io.BytesIO()
                    im.save(buf, "JPEG", quality=94, subsampling=0)
                    dst.writestr(name, buf.getvalue())
                writer.writerow([row.source, name, row.tma, row.status, row.raw])
            dst.writestr("laporan_rename.csv", "\ufeff" + sheet.getvalue())
        os.replace(temp_path, output)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
