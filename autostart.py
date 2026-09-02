"""Enable / disable "start Glance when Windows starts" via the HKCU Run key."""

import os
import sys

try:
    import winreg
except ImportError:  # non-Windows, keeps imports safe
    winreg = None

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE = "Glance"


def _command():
    if getattr(sys, "frozen", False):
        return '"%s"' % os.path.abspath(sys.executable)
    # running from source: use pythonw.exe so no console window
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else sys.executable
    script = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
    return '"%s" "%s"' % (exe, script)


def is_enabled():
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            val, _ = winreg.QueryValueEx(k, _VALUE)
            return bool(val)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def set_enabled(enabled):
    if winreg is None:
        return
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
        if enabled:
            winreg.SetValueEx(k, _VALUE, 0, winreg.REG_SZ, _command())
        else:
            try:
                winreg.DeleteValue(k, _VALUE)
            except FileNotFoundError:
                pass


def toggle():
    new = not is_enabled()
    set_enabled(new)
    return new
