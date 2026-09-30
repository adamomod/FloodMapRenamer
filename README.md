# Flood Map Renamer

Aplikasi desktop Windows untuk membaca label TMA di pojok kanan atas gambar dan mengganti nama seluruh JPG/JPEG dari satu ZIP. Hasilnya ZIP baru dengan gambar JPEG dan `laporan_rename.csv`; ZIP asli tetap utuh.

## Pola nama

`NamaKali_ZonaNomor_LokasiDAS_RatauSNilaiTMA.jpg`

Contoh untuk parameter `Grogol`, `1`, `Hulu`, dan TMA `3015`:

- Terrain → `Grogol_Zona1_Hulu_R3015.jpg`
- Satellite → `Grogol_Zona1_Hulu_S3015.jpg`

Huruf `R` dan `S` membedakan basemap sesuai urutan Terrain/Satellite. Bila kode tersebut ternyata memiliki arti berbeda dalam data Anda, ubah pemetaan `letter` di `renamer.py` sebelum build. Bila tulisan TMA pada gambar berbentuk `3.015`, nama hasil menjadi `3015` (titik/koma dibuang, nol tetap dipertahankan). Periksa interpretasi angka pada tabel sebelum ekspor.

## Pemakaian

1. Klik dua kali `FloodMapRenamer.exe` (setelah dibuat pada Windows, petunjuk di bawah).
2. Pilih **Terrain** atau **Satellite**, lalu isi **Nama Kali**, **Nomor Zona**, **Lokasi DAS** dari kiri ke kanan. Nomor zona boleh `1` atau `Zona1`.
3. Pilih satu ZIP yang berisi gambar dari **satu jenis basemap**. Folder di dalam ZIP boleh digunakan. Gambar selain JPG/JPEG diabaikan.
4. Klik **Baca TMA**. Pilih tiap baris untuk melihat crop kanan atas dan teks OCR. Klik dua kali sel **TMA**, ketik angka koreksi, lalu tekan Enter bila statusnya `PERIKSA` atau hasilnya keliru.
5. Klik **Generate ZIP hasil**, pilih lokasi simpan. ZIP hasil berisi gambar bernama baru beserta CSV audit. Ulangi dengan ZIP basemap lainnya.

Jika gambar yang berbeda memiliki TMA sama dalam ZIP yang sama, nama tujuan akan identik. Aplikasi menghentikan ekspor agar tidak ada gambar yang tertimpa. Pisahkan gambar tersebut ke ZIP berbeda berdasarkan parameter lokasi/zona atau tinjau apakah label OCR keliru.

OCR tidak bisa dijamin benar untuk semua resolusi, bahasa, dan rancangan label. Tabel pratinjau adalah pemeriksaan wajib terutama untuk nilai ambigu. Belum ada contoh screenshot pengguna dalam paket ini, sehingga akurasi pada layout peta asli belum diuji.

## Membuat .exe satu klik

Build `.exe` Windows harus berjalan pada Windows. Paket ini berisi GitHub Actions yang membangun **satu** `FloodMapRenamer.exe` dengan Tesseract OCR dan model bahasa Inggris di dalamnya. Setelah build, pemakai akhir hanya perlu menjalankan file `.exe` tanpa memasang Python/Tesseract.

1. Buat repo GitHub kosong, unggah **isi folder `FloodMapRenamer`** (termasuk folder `.github`), lalu buka tab **Actions**.
2. Pilih **Build Windows EXE** → **Run workflow**.
3. Setelah job sukses, unduh artifact **FloodMapRenamer-Windows**, ekstrak, lalu jalankan `FloodMapRenamer.exe` pada Windows 10/11.

Alternatif build di Windows lokal: pasang Python 3.12, Tesseract OCR dengan `eng.traineddata`, lalu dari PowerShell pada folder ini jalankan:

```powershell
python -m pip install -r requirements-build.txt
$ocr = (Get-Command tesseract.exe).Source
$root = Split-Path $ocr
python -m PyInstaller --noconfirm --clean --onefile --windowed --name FloodMapRenamer --add-data "${root};tesseract" app.py
```

Output ada di `dist/FloodMapRenamer.exe`. Untuk mencoba dari source Python, `python -m pip install Pillow` dan instal Tesseract ke PATH, lalu jalankan `python app.py`.

## Batasan praktis

- Maksimum 10.000 gambar; 40 MB per gambar; total tidak terkompresi 2 GB.
- ZIP output mengganti ekstensi menjadi `.jpg` dan menyimpan ulang JPEG pada kualitas 94. Kompresi ulang dapat mengubah piksel sedikit.
- OCR hanya membaca sekitar 42% lebar kanan dan 31% tinggi atas. Jika label TMA di posisi lain, atur koordinat crop di `detect_tma()`.
- Isi ZIP hanya dibaca sebagai stream; path internal tidak diekstrak ke komputer. Gambar disimpan datar di ZIP hasil.
- Program memerlukan ruang disk untuk ZIP hasil; ekspor memakai file sementara dan hanya mengganti hasil setelah sukses.
