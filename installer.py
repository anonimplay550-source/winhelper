# -*- coding: utf-8 -*-
"""
WinHelper Setup — установщик.
Собирается в один .exe через build.bat.
Также запускается напрямую: python installer.py
"""

import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import shutil
import subprocess
import tempfile
import winreg


APP_NAME = "WinHelper Ultimate"
APP_VERSION = "4.6.0"
APP_PUBLISHER = "WinHelper Project"
APP_EXE_NAME = "WinHelper.exe"
APP_ID = "WinHelperUltimate"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\WinHelperUltimate"

# Куда ставить по умолчанию
DEFAULT_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "WinHelper"
)

# ---------- Утилиты ----------

def resource_path(rel):
    """Путь к ресурсу — работает и в dev, и внутри PyInstaller --onefile."""
    try:
        base = sys._MEIPASS
    except Exception:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, rel)


def find_payload():
    """
    Ищем WinHelper.exe или winhelper.py рядом со сценарием / внутри _MEIPASS.
    Возвращает (путь, тип) где тип = 'exe' | 'py'.
    """
    candidates = [
        (resource_path(APP_EXE_NAME), 'exe'),
        (resource_path("winhelper.py"), 'py'),
        (os.path.join(os.path.dirname(os.path.abspath(__file__)), APP_EXE_NAME), 'exe'),
        (os.path.join(os.path.dirname(os.path.abspath(__file__)), "winhelper.py"), 'py'),
        (os.path.join(os.path.dirname(os.path.abspath(sys.executable)), APP_EXE_NAME), 'exe'),
    ]
    for path, kind in candidates:
        if os.path.exists(path):
            return path, kind
    return None, None


def make_shortcut(lnk_path, target_path, args="", icon_path=None,
                  working_dir=None, description=""):
    """Создаёт .lnk через PowerShell (без pywin32)."""
    try:
        icon_part = f'$s.IconLocation = "{icon_path}";' if icon_path else ""
        wd_part = f'$s.WorkingDirectory = "{working_dir}";' if working_dir else ""
        ps = (
            f'$wsh = New-Object -ComObject WScript.Shell; '
            f'$s = $wsh.CreateShortcut("{lnk_path}"); '
            f'$s.TargetPath = "{target_path}"; '
            f'$s.Arguments = "{args}"; '
            f'{wd_part}'
            f'{icon_part}'
            f'$s.Description = "{description}"; '
            f'$s.Save()'
        )
        subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       capture_output=True, timeout=15,
                       creationflags=0x08000000)
        return True
    except Exception:
        return False


def register_uninstall(install_dir, uninstaller_path, size_kb):
    """Прописываемся в реестр как обычная программа."""
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY,
                                0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, "DisplayName", 0, winreg.REG_SZ, APP_NAME)
            winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(k, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
            winreg.SetValueEx(k, "InstallLocation", 0, winreg.REG_SZ, install_dir)
            winreg.SetValueEx(k, "UninstallString", 0, winreg.REG_SZ,
                              f'"{uninstaller_path}"')
            winreg.SetValueEx(k, "QuietUninstallString", 0, winreg.REG_SZ,
                              f'"{uninstaller_path}" /S')
            winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
            try:
                winreg.SetValueEx(k, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)
            except Exception:
                pass
    except Exception as e:
        print(f"[Registry] {e}")


# ============================================================
#                       УСТАНОВЩИК
# ============================================================
class InstallerApp:
    # Цвета в стиле современных установщиков
    BG          = "#0e1116"
    CARD        = "#171b23"
    ACCENT      = "#4cc2ff"
    ACCENT_DARK = "#2a8ac4"
    TEXT        = "#e6edf3"
    TEXT_DIM    = "#8b949e"
    BORDER      = "#2a3038"
    SUCCESS     = "#3fb950"
    ERROR       = "#f85149"

    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} — Установка")
        self.root.geometry("640x440")
        self.root.resizable(False, False)
        self.root.configure(bg=self.BG)
        self._center_window(640, 440)

        try:
            self.root.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

        # Данные установки
        self.install_dir = tk.StringVar(value=DEFAULT_DIR)
        self.opt_desktop = tk.BooleanVar(value=True)
        self.opt_startmenu = tk.BooleanVar(value=True)
        self.opt_autostart = tk.BooleanVar(value=False)
        self.opt_launch = tk.BooleanVar(value=True)

        # Состояние прогресса
        self._cancel = False
        self._payload_path, self._payload_kind = find_payload()

        # Общий контейнер для страниц
        self.container = tk.Frame(self.root, bg=self.BG)
        self.container.pack(fill="both", expand=True)

        self._build_bottombar()
        self.show_welcome()

    # ---------- Окно ----------
    def _center_window(self, w, h):
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    # ---------- Нижняя панель с кнопками ----------
    def _build_bottombar(self):
        bar = tk.Frame(self.root, bg=self.CARD, height=60)
        bar.pack(side="bottom", fill="x")
        bar.pack_propagate(False)
        tk.Frame(self.root, bg=self.BORDER, height=1).pack(side="bottom", fill="x")

        self.btn_cancel = tk.Button(
            bar, text="Отмена", command=self._on_cancel,
            bg=self.CARD, fg=self.TEXT, activebackground=self.BORDER,
            activeforeground=self.TEXT, relief="flat",
            font=("Segoe UI", 10), width=12, cursor="hand2")
        self.btn_cancel.pack(side="right", padx=(5, 15), pady=12)

        self.btn_next = tk.Button(
            bar, text="Далее  →", command=self._on_next,
            bg=self.ACCENT, fg="#0e1116", activebackground=self.ACCENT_DARK,
            activeforeground="#0e1116", relief="flat",
            font=("Segoe UI", 10, "bold"), width=14, cursor="hand2")
        self.btn_next.pack(side="right", pady=12)

        self.btn_back = tk.Button(
            bar, text="←  Назад", command=self._on_back,
            bg=self.CARD, fg=self.TEXT_DIM, activebackground=self.BORDER,
            activeforeground=self.TEXT, relief="flat",
            font=("Segoe UI", 10), width=12, cursor="hand2", state="disabled")
        self.btn_back.pack(side="right", padx=5, pady=12)

    # ---------- Страницы ----------
    def _clear(self):
        for w in self.container.winfo_children():
            w.destroy()

    def show_welcome(self):
        self._page = "welcome"
        self._clear()
        self.btn_back.config(state="disabled")
        self.btn_next.config(text="Установить  →", state="normal")

        wrap = tk.Frame(self.container, bg=self.BG)
        wrap.pack(fill="both", expand=True, padx=40, pady=(35, 20))

        tk.Label(wrap, text="🪟", font=("Segoe UI Emoji", 48),
                 bg=self.BG, fg=self.ACCENT).pack(anchor="w")

        tk.Label(wrap, text=f"Установка {APP_NAME}",
                 font=("Segoe UI", 20, "bold"), bg=self.BG,
                 fg=self.TEXT).pack(anchor="w", pady=(10, 5))

        tk.Label(wrap, text=f"Версия {APP_VERSION}",
                 font=("Segoe UI", 11), bg=self.BG,
                 fg=self.TEXT_DIM).pack(anchor="w")

        desc = ("Мастер установит WinHelper Ultimate на ваш компьютер.\n"
                "Будут созданы ярлыки и запись в списке установленных программ.\n\n"
                "Нажмите «Установить», чтобы продолжить.")
        tk.Label(wrap, text=desc, font=("Segoe UI", 10), bg=self.BG,
                 fg=self.TEXT_DIM, justify="left").pack(anchor="w", pady=(25, 0))

        if not self._payload_path:
            tk.Label(wrap,
                     text="⚠ Не найден файл WinHelper (winhelper.py или WinHelper.exe)",
                     font=("Segoe UI", 9, "bold"), bg=self.BG,
                     fg=self.ERROR).pack(anchor="w", pady=(20, 0))

    def show_options(self):
        self._page = "options"
        self._clear()
        self.btn_back.config(state="normal")
        self.btn_next.config(text="Установить  →", state="normal")

        wrap = tk.Frame(self.container, bg=self.BG)
        wrap.pack(fill="both", expand=True, padx=40, pady=(30, 20))

        tk.Label(wrap, text="Параметры установки",
                 font=("Segoe UI", 16, "bold"), bg=self.BG,
                 fg=self.TEXT).pack(anchor="w", pady=(0, 20))

        # Путь
        tk.Label(wrap, text="Папка установки:",
                 font=("Segoe UI", 10), bg=self.BG,
                 fg=self.TEXT_DIM).pack(anchor="w")
        row = tk.Frame(wrap, bg=self.BG)
        row.pack(fill="x", pady=(5, 15))
        ent = tk.Entry(row, textvariable=self.install_dir,
                       font=("Segoe UI", 10), bg=self.CARD, fg=self.TEXT,
                       insertbackground=self.TEXT, relief="flat",
                       highlightthickness=1, highlightbackground=self.BORDER,
                       highlightcolor=self.ACCENT)
        ent.pack(side="left", fill="x", expand=True, ipady=6)
        tk.Button(row, text="Обзор…", command=self._pick_dir,
                  bg=self.CARD, fg=self.TEXT, activebackground=self.BORDER,
                  relief="flat", font=("Segoe UI", 9), cursor="hand2",
                  padx=12, pady=4).pack(side="left", padx=(8, 0))

        # Компоненты
        tk.Label(wrap, text="Дополнительно:",
                 font=("Segoe UI", 10), bg=self.BG,
                 fg=self.TEXT_DIM).pack(anchor="w", pady=(5, 5))

        for var, label in [
            (self.opt_desktop, "Создать ярлык на Рабочем столе"),
            (self.opt_startmenu, "Добавить в меню «Пуск»"),
            (self.opt_autostart, "Запускать WinHelper при входе в Windows"),
            (self.opt_launch, "Запустить WinHelper после установки"),
        ]:
            self._make_check(wrap, var, label)

    def _make_check(self, parent, var, label):
        row = tk.Frame(parent, bg=self.BG)
        row.pack(anchor="w", pady=2)
        cb = tk.Checkbutton(row, text=label, variable=var,
                            bg=self.BG, fg=self.TEXT, selectcolor=self.CARD,
                            activebackground=self.BG, activeforeground=self.TEXT,
                            font=("Segoe UI", 10), cursor="hand2",
                            bd=0, highlightthickness=0, anchor="w")
        cb.pack(side="left")

    def _pick_dir(self):
        d = filedialog.askdirectory(initialdir=self.install_dir.get() or DEFAULT_DIR,
                                    title="Выберите папку установки")
        if d:
            self.install_dir.set(os.path.join(d, "WinHelper"))

    def show_progress(self):
        self._page = "progress"
        self._clear()
        self.btn_back.config(state="disabled")
        self.btn_next.config(text="Установка…", state="disabled")
        self.btn_cancel.config(text="Отмена", state="normal")

        wrap = tk.Frame(self.container, bg=self.BG)
        wrap.pack(fill="both", expand=True, padx=40, pady=(30, 10))

        tk.Label(wrap, text="Идёт установка…",
                 font=("Segoe UI", 16, "bold"), bg=self.BG,
                 fg=self.TEXT).pack(anchor="w")

        # Progress bar (canvas — свой стиль)
        self.pb_frame = tk.Frame(wrap, bg=self.CARD, height=22,
                                  highlightthickness=1,
                                  highlightbackground=self.BORDER)
        self.pb_frame.pack(fill="x", pady=(20, 8))
        self.pb_frame.pack_propagate(False)
        self.pb_fill = tk.Frame(self.pb_frame, bg=self.ACCENT)
        self.pb_fill.place(x=0, y=0, relwidth=0, relheight=1)

        # Строка статуса
        self.lbl_status = tk.Label(wrap, text="Подготовка…",
                                   font=("Segoe UI", 10), bg=self.BG,
                                   fg=self.TEXT, anchor="w")
        self.lbl_status.pack(fill="x")

        info = tk.Frame(wrap, bg=self.BG)
        info.pack(fill="x", pady=(6, 0))
        self.lbl_speed = tk.Label(info, text="— MB/s",
                                  font=("Consolas", 10), bg=self.BG,
                                  fg=self.TEXT_DIM)
        self.lbl_speed.pack(side="left")
        self.lbl_eta = tk.Label(info, text="Осталось: —",
                                font=("Consolas", 10), bg=self.BG,
                                fg=self.TEXT_DIM)
        self.lbl_eta.pack(side="right")

        # Лог файлов (как в торрентах)
        log_frame = tk.Frame(wrap, bg=self.CARD,
                              highlightthickness=1, highlightbackground=self.BORDER)
        log_frame.pack(fill="both", expand=True, pady=(12, 0))
        self.log = tk.Listbox(log_frame, bg=self.CARD, fg=self.TEXT_DIM,
                              font=("Consolas", 9), relief="flat",
                              highlightthickness=0, activestyle="none")
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

        # Запускаем установку в фоне
        threading.Thread(target=self._do_install, daemon=True).start()

    # ---------- Навигация ----------
    def _on_next(self):
        if self._page == "welcome":
            if not self._payload_path:
                messagebox.showerror("Ошибка",
                    "Не найден winhelper.py или WinHelper.exe рядом с установщиком.")
                return
            self.show_options()
        elif self._page == "options":
            self._start_install()

    def _on_back(self):
        if self._page == "options":
            self.show_welcome()

    def _on_cancel(self):
        if self._page == "progress":
            self._cancel = True
            self.root.after(200, self.root.destroy)
        else:
            self.root.destroy()

    def _start_install(self):
        try:
            os.makedirs(self.install_dir.get(), exist_ok=True)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать папку:\n{e}")
            return
        self.show_progress()

    # ---------- Прогресс ----------
    def _set_progress(self, fraction, status=None, speed=None, eta=None):
        try:
            fraction = max(0.0, min(1.0, fraction))
            self.pb_fill.place_configure(relwidth=fraction)
            if status is not None:
                self.lbl_status.config(text=status)
            if speed is not None:
                self.lbl_speed.config(text=f"{speed:.1f} MB/s")
            if eta is not None:
                self.lbl_eta.config(text=f"Осталось: {int(eta)} с")
        except Exception:
            pass

    def _log_add(self, text):
        try:
            self.log.insert(tk.END, text)
            self.log.see(tk.END)
            if self.log.size() > 200:
                self.log.delete(0, 50)
        except Exception:
            pass

    # ---------- Основная логика установки ----------
    def _do_install(self):
        try:
            t_start = time.time()
            target = self.install_dir.get()
            os.makedirs(target, exist_ok=True)

            # Собираем список «файлов» для имитации скорости
            # Настоящий вес — размер исходников + наш логотип-заглушка
            payload_path, kind = self._payload_path, self._payload_kind
            payload_size = os.path.getsize(payload_path) if os.path.exists(payload_path) else 0
            total_bytes = max(payload_size, 1)

            # Шаг 1: главный файл
            self.root.after(0, lambda: self._set_progress(0.0, "Установка WinHelper…", 0, 0))
            time.sleep(0.3)

            dst_main = os.path.join(target, "winhelper.py" if kind == "py" else APP_EXE_NAME)
            bytes_done = 0
            chunk = 65536
            with open(payload_path, 'rb') as src, open(dst_main, 'wb') as dst:
                while True:
                    if self._cancel:
                        return
                    buf = src.read(chunk)
                    if not buf:
                        break
                    dst.write(buf)
                    bytes_done += len(buf)
                    # Считаем «скорость» как реальный темп записи
                    elapsed = max(time.time() - t_start, 0.001)
                    speed = bytes_done / elapsed / 1048576  # MB/s
                    # Принудительный «торрент-темп» — не быстрее 25 MB/s
                    if speed > 25:
                        time.sleep(0.015)
                        elapsed = max(time.time() - t_start, 0.001)
                        speed = bytes_done / elapsed / 1048576
                    frac = 0.05 + 0.55 * (bytes_done / total_bytes)
                    eta = (total_bytes - bytes_done) / (speed * 1048576) if speed > 0 else 0
                    self.root.after(0, lambda f=frac, s=speed, e=eta: self._set_progress(
                        f, f"Распаковка: winhelper.{'py' if kind=='py' else 'exe'}",
                        s, e))

            self.root.after(0, lambda: self._log_add(
                f"✓  {os.path.basename(dst_main)}  ({total_bytes/1048576:.2f} MB)"))

            # Шаг 2: создаём launcher.bat (для .py-версии)
            if kind == "py":
                bat_path = os.path.join(target, "WinHelper.bat")
                bat_src = (
                    "@echo off\r\n"
                    "cd /d \"%~dp0\"\r\n"
                    "start \"\" pythonw \"%~dp0winhelper.py\"\r\n"
                    "exit\r\n"
                )
                with open(bat_path, 'w', encoding='cp866') as f:
                    f.write(bat_src)
                self.root.after(0, lambda: self._log_add("✓  WinHelper.bat"))
                target_exe = bat_path
            else:
                target_exe = dst_main

            self.root.after(0, lambda: self._set_progress(0.65, "Копирование uninstall…", 0, 0))

            # Шаг 3: копируем удалятор
            uninstall_src = resource_path("uninstall.py")
            if not os.path.exists(uninstall_src):
                uninstall_src = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                              "uninstall.py")
            uninstall_dst = os.path.join(target, "uninstall.py")
            if os.path.exists(uninstall_src):
                shutil.copy2(uninstall_src, uninstall_dst)
                self.root.after(0, lambda: self._log_add("✓  uninstall.py"))
            else:
                # Пишем встроенный удалятор, если файл не найден
                with open(uninstall_dst, 'w', encoding='utf-8') as f:
                    f.write(self._embedded_uninstall(target))
                self.root.after(0, lambda: self._log_add("✓  uninstall.py (встроенный)"))

            self.root.after(0, lambda: self._set_progress(0.75, "Создание ярлыков…", 0, 0))
            time.sleep(0.2)

            # Шаг 4: ярлыки
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            start_menu = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")),
                                      "Microsoft", "Windows", "Start Menu", "Programs")

            if self.opt_desktop.get():
                lnk = os.path.join(desktop, f"{APP_NAME}.lnk")
                make_shortcut(lnk, target_exe,
                              working_dir=target,
                              description=APP_NAME)
                self.root.after(0, lambda: self._log_add("✓  Ярлык на Рабочем столе"))

            if self.opt_startmenu.get():
                os.makedirs(start_menu, exist_ok=True)
                lnk = os.path.join(start_menu, f"{APP_NAME}.lnk")
                make_shortcut(lnk, target_exe,
                              working_dir=target,
                              description=APP_NAME)
                self.root.after(0, lambda: self._log_add("✓  Ярлык в Пуске"))

            if self.opt_autostart.get():
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_CURRENT_USER,
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                        0, winreg.KEY_SET_VALUE) as k:
                        winreg.SetValueEx(k, "WinHelper", 0, winreg.REG_SZ,
                                          f'"{target_exe}"')
                    self.root.after(0, lambda: self._log_add("✓  Добавлено в автозагрузку"))
                except Exception:
                    pass

            self.root.after(0, lambda: self._set_progress(0.9, "Регистрация…", 0, 0))

            # Шаг 5: реестр (Uninstall)
            try:
                size_kb = int(total_bytes / 1024)
            except Exception:
                size_kb = 0
            register_uninstall(target, uninstall_dst, size_kb)
            self.root.after(0, lambda: self._log_add("✓  Запись в реестре"))

            self.root.after(0, lambda: self._set_progress(1.0, "Готово!", 0, 0))
            time.sleep(0.4)

            # Финал
            self.root.after(0, lambda: self.show_finish(target_exe))

        except Exception as e:
            err = str(e)
            self.root.after(0, lambda: self._install_failed(err))

    def _install_failed(self, err):
        messagebox.showerror("Ошибка установки", err)
        self._page = "welcome"
        self.show_welcome()

    # ---------- Финал ----------
    def show_finish(self, target_exe):
        self._page = "finish"
        self._clear()
        self.btn_back.config(state="disabled")
        self.btn_cancel.config(text="Закрыть", command=self.root.destroy,
                                state="normal")
        self.btn_next.config(text="Запустить  ✓", state="normal",
                              command=lambda: self._finish_launch(target_exe))

        wrap = tk.Frame(self.container, bg=self.BG)
        wrap.pack(fill="both", expand=True, padx=40, pady=(35, 20))

        tk.Label(wrap, text="✓", font=("Segoe UI", 60, "bold"),
                 bg=self.BG, fg=self.SUCCESS).pack(anchor="w")

        tk.Label(wrap, text="Установка завершена!",
                 font=("Segoe UI", 20, "bold"), bg=self.BG,
                 fg=self.TEXT).pack(anchor="w", pady=(10, 5))

        tk.Label(wrap,
                 text=f"{APP_NAME} {APP_VERSION} успешно установлен.\n"
                      f"Папка: {self.install_dir.get()}",
                 font=("Segoe UI", 10), bg=self.BG,
                 fg=self.TEXT_DIM, justify="left").pack(anchor="w", pady=(5, 25))

        self._make_check(wrap, self.opt_launch,
                          "Запустить WinHelper прямо сейчас")

    def _finish_launch(self, target_exe):
        if self.opt_launch.get():
            try:
                if target_exe.lower().endswith(".bat"):
                    subprocess.Popen(['cmd', '/c', target_exe],
                                      cwd=os.path.dirname(target_exe),
                                      creationflags=0x08000000)
                else:
                    subprocess.Popen([target_exe],
                                      cwd=os.path.dirname(target_exe),
                                      creationflags=0x00000008)
            except Exception as e:
                messagebox.showwarning("Не удалось запустить", str(e))
        self.root.destroy()

    # ---------- Встроенный удалятор ----------
    @staticmethod
    def _embedded_uninstall(install_dir):
        return f'''# -*- coding: utf-8 -*-
import os, sys, shutil, winreg, tkinter as tk
from tkinter import messagebox

INSTALL_DIR = r"{install_dir}"
UNINSTALL_KEY = r"{UNINSTALL_KEY}"

def main():
    root = tk.Tk(); root.withdraw()
    if not messagebox.askyesno("Удаление WinHelper",
        "Удалить WinHelper Ultimate и все его ярлыки?"):
        return
    # Реестр
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except Exception:
        pass
    # Ярлыки
    for lnk in [
        os.path.join(os.path.expanduser("~"), "Desktop", "{APP_NAME}.lnk"),
        os.path.join(os.environ.get("APPDATA",""), "Microsoft", "Windows",
                     "Start Menu", "Programs", "{APP_NAME}.lnk"),
    ]:
        try: os.remove(lnk)
        except Exception: pass
    # Автозагрузка
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
            r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run", 0,
            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, "WinHelper")
    except Exception: pass
    # Папка (отложенно, т.к. сам скрипт может быть внутри)
    try:
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    except Exception: pass
    messagebox.showinfo("Готово", "WinHelper удалён.")
    root.destroy()

if __name__ == "__main__":
    main()
'''


# ============================================================
#                       ЗАПУСК
# ============================================================
if __name__ == "__main__":
    root = tk.Tk()
    app = InstallerApp(root)
    root.mainloop()