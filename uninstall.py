# -*- coding: utf-8 -*-
"""WinHelper — деинсталлятор. Устанавливается вместе с программой."""
import os
import sys
import shutil
import winreg
import tkinter as tk
from tkinter import messagebox

APP_NAME = "WinHelper Ultimate"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\WinHelperUltimate"

# Папка — откуда запущен этот скрипт (или .exe)
if getattr(sys, 'frozen', False):
    INSTALL_DIR = os.path.dirname(sys.executable)
else:
    INSTALL_DIR = os.path.dirname(os.path.abspath(__file__))


def remove_shortcuts():
    paths = [
        os.path.join(os.path.expanduser("~"), "Desktop", f"{APP_NAME}.lnk"),
        os.path.join(os.environ.get("APPDATA", ""),
                     "Microsoft", "Windows", "Start Menu", "Programs",
                     f"{APP_NAME}.lnk"),
    ]
    for p in paths:
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def remove_autostart():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, "WinHelper")
    except Exception:
        pass


def remove_registry():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except Exception:
        pass


def main():
    root = tk.Tk()
    root.withdraw()
    if not messagebox.askyesno(
        "Удаление WinHelper",
        f"Удалить {APP_NAME}?\n\nПапка: {INSTALL_DIR}\n\n"
        "Все ярлыки, запись в реестре и настройки будут удалены."
    ):
        return

    remove_shortcuts()
    remove_autostart()
    remove_registry()

    # Папку удалим через отдельный cmd.exe — чтобы сам удалятор не блокировал её
    try:
        bat = (
            '@echo off\r\n'
            'timeout /t 2 /nobreak >nul\r\n'
            f'rmdir /s /q "{INSTALL_DIR}"\r\n'
            'exit\r\n'
        )
        tmp = os.path.join(os.environ.get("TEMP", "."), "wh_uninstall.bat")
        with open(tmp, "w", encoding="cp866") as f:
            f.write(bat)
        os.startfile(tmp)
    except Exception:
        shutil.rmtree(INSTALL_DIR, ignore_errors=True)

    messagebox.showinfo("Готово", "WinHelper успешно удалён.")
    root.destroy()


if __name__ == "__main__":
    main()