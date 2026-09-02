"""Speak an English word using the Windows built-in speech synthesizer."""

import re
import subprocess
import threading

_SAFE = re.compile(r"[^A-Za-z '\-]")
_CREATE_NO_WINDOW = 0x08000000


def speak(word):
    w = _SAFE.sub("", str(word or "")).strip().replace("'", "''")
    if not w:
        return

    def run():
        ps = (
            "Add-Type -AssemblyName System.Speech;"
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
            "$s.Rate = -1;"
            "$s.Speak('%s')" % w
        )
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                creationflags=_CREATE_NO_WINDOW,
                timeout=15,
            )
        except Exception:
            pass

    threading.Thread(target=run, daemon=True).start()
