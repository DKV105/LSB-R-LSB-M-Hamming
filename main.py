import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image  # Pillow – обязательная зависимость

import lsb_replacement
import lsb_matching
import hamming_code


class StegoApp(tk.Tk):
    """Главное окно: три вкладки с методами стеганографии."""

    def __init__(self):
        super().__init__()
        self.title("Steganography Lab – LSB & Hamming")
        self.geometry("640x420")
        self.resizable(False, False)

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        # Добавляем вкладки с уникальным суффиксом для выходного файла
        notebook.add(MethodTab(notebook, "LSB Replacement", lsb_replacement, "lsbr"), text="LSB-R")
        notebook.add(MethodTab(notebook, "LSB Matching", lsb_matching, "lsbm"), text="LSB-M")
        notebook.add(MethodTab(notebook, "Hamming (15,11)", hamming_code, "ham"), text="Hamming")


class MethodTab(ttk.Frame):
    """Одна вкладка: выбор файла, ввод сообщения, рейт, Embed/Extract."""

    def __init__(self, parent, label: str, backend, tag: str):
        super().__init__(parent)
        self.backend = backend
        self.tag = tag  # идёт в имя выходного файла

        # ------ переменные интерфейса ------
        self.image_path = tk.StringVar()
        self.payload_text = tk.StringVar()
        self.rate = tk.DoubleVar(value=1.0)  # 1.0 = Rmax
        self.rate_str = tk.StringVar(value=f"{self.rate.get():.2f}")
        self.rate.trace_add("write", lambda *_, sv=self.rate_str, rv=self.rate: sv.set(f"{rv.get():.2f}"))

        # ------ размещение ------
        row = 0
        ttk.Label(self, text=label, font=("Segoe UI", 12, "bold")).grid(row=row, column=0, columnspan=3, pady=(10, 5))

        row += 1
        ttk.Label(self, text="Image").grid(row=row, column=0, sticky="e", padx=5)
        ttk.Entry(self, textvariable=self.image_path, width=45).grid(row=row, column=1, padx=5)
        ttk.Button(self, text="Browse…", command=self.browse_image).grid(row=row, column=2, padx=5)

        row += 1
        ttk.Label(self, text="Message / Hex").grid(row=row, column=0, sticky="e", padx=5)
        ttk.Entry(self, textvariable=self.payload_text, width=45).grid(row=row, column=1, padx=5)
        ttk.Button(self, text="Load file…", command=self.load_payload_file).grid(row=row, column=2, padx=5)

        row += 1
        ttk.Label(self, text="Rate (0.0 – 1.0 Rmax)").grid(row=row, column=0, sticky="e", padx=5)
        ttk.Scale(self, variable=self.rate, from_=0.0, to=1.0, orient="horizontal", length=200).grid(row=row, column=1, padx=5, sticky="ew")
        ttk.Label(self, textvariable=self.rate_str, width=5).grid(row=row, column=2, padx=5)

        row += 1
        ttk.Button(self, text="Embed", width=15, command=self.embed).grid(row=row, column=0, pady=15)
        ttk.Button(self, text="Extract", width=15, command=self.extract).grid(row=row, column=1, pady=15)
        self.status = ttk.Label(self, text="")
        self.status.grid(row=row + 1, column=0, columnspan=3)

        for child in self.winfo_children():
            child.grid_configure(pady=2)

    # ------ callbacks ------
    def browse_image(self):
        path = filedialog.askopenfilename(title="Select 24-bit BMP image", filetypes=[("Bitmap images", "*.bmp")])
        if path:
            self.image_path.set(path)

    def load_payload_file(self):
        path = filedialog.askopenfilename(title="Select payload file")
        if not path:
            return
        with open(path, "rb") as f:
            data = f.read()
        self.payload_text.set(data.hex())

    def embed(self):
        img = self.image_path.get()
        if not img:
            messagebox.showwarning("No image", "Choose a BMP first.")
            return
        payload_raw = self.payload_text.get().strip()
        if not payload_raw:
            messagebox.showwarning("No payload", "Enter message or choose file.")
            return

        try:
            if all(c in "0123456789abcdefABCDEF" for c in payload_raw) and len(payload_raw) % 2 == 0:
                payload_bytes = bytes.fromhex(payload_raw)
            else:
                payload_bytes = payload_raw.encode()
        except ValueError as err:
            messagebox.showerror("Payload error", f"Cannot parse payload: {err}")
            return

        out_path = self._output_path(img, self.tag)
        try:
            self.backend.embed(img, payload_bytes, self.rate.get(), out_path)
            self.status.config(text=f"Embedded → {os.path.basename(out_path)}")
        except Exception as exc:
            messagebox.showerror("Embed failed", str(exc))

    def extract(self):
        img = self.image_path.get()
        if not img:
            messagebox.showwarning("No image", "Choose a stego-BMP first.")
            return
        try:
            # Передаём значение рейта, если метод поддерживает его
            if hasattr(self.backend.extract, '__code__') and self.backend.extract.__code__.co_argcount == 2:
                data = self.backend.extract(img, self.rate.get())
            else:
                data = self.backend.extract(img)

            try:
                text = data.decode()
                messagebox.showinfo("Extracted payload", text)
            except UnicodeDecodeError:
                messagebox.showinfo("Extracted payload (hex)", data.hex())
        except Exception as exc:
            messagebox.showerror("Extraction failed", str(exc))

    # ------ helper ------
    @staticmethod
    def _output_path(path: str, tag: str) -> str:
        base, ext = os.path.splitext(path)
        return f"{base}_stego_{tag}{ext}"


if __name__ == "__main__":
    StegoApp().mainloop()
