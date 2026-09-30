"""One-click Windows UI for flood map ZIP renaming."""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageOps, ImageTk
import zipfile

from renamer import Row, build_names, export_zip, normalize_tma, scan


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Flood Map Renamer — TMA OCR")
        self.geometry("1060x700")
        self.minsize(900, 590)
        self.rows: list[Row] = []
        self.zip_path = ""
        self.busy = False
        self.photo = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")

        top = ttk.Frame(self, padding=16)
        top.grid(row=0, column=0, sticky="ew")
        for c in range(4):
            top.columnconfigure(c, weight=1)
        ttk.Label(top, text="Flood Map Renamer", font=("Segoe UI", 19, "bold")).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(top, text="1  Basemap       2  Parameter       3  ZIP gambar       4  Baca TMA       5  Periksa & ekspor",
                  foreground="#315f87").grid(row=1, column=0, columnspan=4, sticky="w", pady=(2, 14))

        self.basemap = tk.StringVar(value="Terrain")
        self.kali = tk.StringVar()
        self.zona = tk.StringVar()
        self.lokasi = tk.StringVar()
        fields = [("Basemap", self.basemap), ("Nama Kali", self.kali), ("Nomor Zona", self.zona), ("Lokasi DAS", self.lokasi)]
        for i, (title, variable) in enumerate(fields):
            ttk.Label(top, text=title).grid(row=2, column=i, sticky="w", padx=(0, 10))
            if i == 0:
                widget = ttk.Combobox(top, textvariable=variable, values=["Terrain", "Satellite"], state="readonly")
            else:
                widget = ttk.Entry(top, textvariable=variable)
            widget.grid(row=3, column=i, sticky="ew", padx=(0, 12), pady=(2, 8))
        ttk.Label(top, text="Contoh: Grogol  |  1  |  Hulu  →  Grogol_Zona1_Hulu_R3015.jpg (Terrain) / S3015.jpg (Satellite)",
                  foreground="#52667a").grid(row=4, column=0, columnspan=4, sticky="w")

        bar = ttk.Frame(self, padding=(16, 4, 16, 8))
        bar.grid(row=1, column=0, sticky="ew")
        self.choose_btn = ttk.Button(bar, text="Pilih ZIP gambar…", command=self.choose_zip)
        self.choose_btn.pack(side="left")
        self.scan_btn = ttk.Button(bar, text="Baca TMA", command=self.start_scan)
        self.scan_btn.pack(side="left", padx=8)
        self.export_btn = ttk.Button(bar, text="Generate ZIP hasil…", command=self.start_export)
        self.export_btn.pack(side="right")
        self.path_label = ttk.Label(bar, text="Belum ada ZIP", width=55)
        self.path_label.pack(side="left", padx=8)

        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.grid(row=2, column=0, sticky="nsew", padx=16)
        left = ttk.Frame(pane)
        right = ttk.Frame(pane, padding=(12, 4))
        pane.add(left, weight=3)
        pane.add(right, weight=2)
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)
        ttk.Label(left, text="Hasil OCR — klik dua kali kolom TMA untuk koreksi", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.table = ttk.Treeview(left, columns=("source", "tma", "status", "name"), show="headings", selectmode="browse")
        for key, title, width in [("source", "File asal", 190), ("tma", "TMA", 74), ("status", "Status", 185), ("name", "Nama hasil", 270)]:
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=65)
        self.table.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=self.table.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.bind("<Double-1>", self.edit_tma)
        self.table.bind("<<TreeviewSelect>>", self.show_selection)
        for var in (self.kali, self.zona, self.lokasi, self.basemap):
            var.trace_add("write", lambda *_: self.refresh_table())

        ttk.Label(right, text="Pratinjau pojok kanan atas", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.preview = ttk.Label(right, text="Pilih gambar dari tabel", anchor="center")
        self.preview.pack(fill="both", expand=True, pady=8)
        ttk.Label(right, text="Teks OCR mentah:").pack(anchor="w")
        self.raw = tk.Text(right, height=5, wrap="word", state="disabled")
        self.raw.pack(fill="x", pady=4)
        ttk.Label(right, text="Nilai meragukan wajib dikoreksi. TMA sama dalam satu ZIP menyebabkan bentrok nama.",
                  wraplength=310, foreground="#79532e").pack(anchor="w", pady=6)

        self.status = tk.StringVar(value="Siap. Masukkan parameter dan pilih ZIP gambar.")
        ttk.Label(self, textvariable=self.status, padding=(16, 10)).grid(row=3, column=0, sticky="ew")

    def choose_zip(self):
        path = filedialog.askopenfilename(filetypes=[("ZIP", "*.zip")])
        if path:
            self.zip_path = path
            self.rows.clear()
            self.path_label.configure(text=Path(path).name)
            self.refresh_table()
            self.status.set("ZIP dipilih. Klik Baca TMA.")

    def run_background(self, job):
        if self.busy:
            return
        self.busy = True
        for btn in (self.choose_btn, self.scan_btn, self.export_btn):
            btn.configure(state="disabled")
        def worker():
            try:
                job()
            except Exception as exc:
                self.after(0, lambda error=str(exc): messagebox.showerror("Proses gagal", error))
            finally:
                self.after(0, self.finish)
        threading.Thread(target=worker, daemon=True).start()

    def finish(self):
        self.busy = False
        for btn in (self.choose_btn, self.scan_btn, self.export_btn):
            btn.configure(state="normal")

    def start_scan(self):
        if not self.zip_path:
            messagebox.showwarning("ZIP belum dipilih", "Pilih ZIP gambar terlebih dahulu.")
            return
        source = self.zip_path
        def job():
            rows = scan(source, lambda n, total: self.after(0, lambda n=n, total=total: self.status.set(f"Membaca TMA: {n}/{total}")))
            def complete():
                if self.zip_path == source:
                    self.rows = rows
                    self.refresh_table()
                    flagged = sum(row.status != "OK" for row in rows)
                    self.status.set(f"Selesai: {len(rows)} gambar. {flagged} nilai perlu diperiksa.")
            self.after(0, complete)
        self.run_background(job)

    def refresh_table(self):
        selected = self.table.selection()
        previous = selected[0] if selected else None
        self.table.delete(*self.table.get_children())
        letter = "R" if self.basemap.get() == "Terrain" else "S"
        for i, row in enumerate(self.rows):
            parts = [self.kali.get().strip().replace(" ", ""), self.zona.get().strip().replace(" ", ""), self.lokasi.get().strip().replace(" ", "")]
            if parts[1] and not parts[1].lower().startswith("zona"):
                parts[1] = "Zona" + parts[1]
            name = "_".join(parts) + f"_{letter}{row.tma}.jpg" if all(parts) and row.tma else "—"
            self.table.insert("", "end", iid=str(i), values=(row.source, row.tma or "—", row.status, name))
        if previous and self.table.exists(previous):
            self.table.selection_set(previous)

    def edit_tma(self, event):
        if self.busy:
            return
        item = self.table.identify_row(event.y)
        col = self.table.identify_column(event.x)
        if not item or col != "#2":
            return
        box = self.table.bbox(item, col)
        if not box:
            return
        x, y, width, height = box
        editor = ttk.Entry(self.table)
        editor.place(x=x, y=y, width=width, height=height)
        editor.insert(0, self.rows[int(item)].tma)
        editor.focus_set()
        editor.select_range(0, "end")
        def commit(_=None):
            if not editor.winfo_exists():
                return
            try:
                normalized = normalize_tma(editor.get())
            except ValueError as exc:
                messagebox.showwarning("TMA tidak valid", str(exc))
                editor.focus_set()
                return
            row = self.rows[int(item)]
            row.tma = normalized
            row.status = "OK"
            editor.destroy()
            self.refresh_table()
            self.table.selection_set(item)
        editor.bind("<Return>", commit)
        editor.bind("<Escape>", lambda _: editor.destroy())

    def show_selection(self, _=None):
        selection = self.table.selection()
        if not selection or not self.zip_path:
            return
        row = self.rows[int(selection[0])]
        self.raw.configure(state="normal")
        self.raw.delete("1.0", "end")
        self.raw.insert("1.0", row.raw)
        self.raw.configure(state="disabled")
        try:
            with zipfile.ZipFile(self.zip_path) as archive, archive.open(row.source) as src, Image.open(src) as im:
                im = ImageOps.exif_transpose(im)
                w, h = im.size
                crop = im.crop((int(.58 * w), 0, w, int(.31 * h)))
                crop.thumbnail((370, 290))
                self.photo = ImageTk.PhotoImage(crop)
                self.preview.configure(image=self.photo, text="")
        except Exception:
            self.preview.configure(image="", text="Pratinjau tidak tersedia")

    def start_export(self):
        if not self.rows:
            messagebox.showwarning("Belum siap", "Klik Baca TMA terlebih dahulu.")
            return
        try:
            names = build_names(self.rows, self.kali.get(), self.zona.get(), self.lokasi.get(), self.basemap.get())
        except ValueError as exc:
            messagebox.showwarning("Periksa parameter", str(exc))
            return
        default = f"{self.kali.get()}_{self.zona.get()}_{self.lokasi.get()}_{self.basemap.get()}_renamed.zip"
        target = filedialog.asksaveasfilename(defaultextension=".zip", initialfile=default, filetypes=[("ZIP", "*.zip")])
        if not target:
            return
        if Path(target).exists() and not messagebox.askyesno("Timpa hasil?", "File ZIP hasil sudah ada. Timpa file tersebut?"):
            return
        source = self.zip_path
        rows = [Row(row.source, row.tma, row.raw, row.status) for row in self.rows]
        def job():
            export_zip(source, target, rows, names)
            self.after(0, lambda: (self.status.set(f"Berhasil: {target}"), messagebox.showinfo("Selesai", f"{len(names)} gambar tersimpan di:\n{target}")))
        self.run_background(job)


if __name__ == "__main__":
    App().mainloop()
