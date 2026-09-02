"""Preview the Glance card with sample data - no hotkey / OCR / network.

    .venv\\Scripts\\python.exe demo.py           # light
    .venv\\Scripts\\python.exe demo.py dark      # dark

Saves demo.png. Click card = next sample, right-click / Esc = close.
"""

import ctypes
import sys
import tkinter as tk

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

import config as cfg_mod
import tts
from popup import Popup

SAMPLES = [
    {
        "word": "resilient", "phonetic": "rɪˈzɪljənt",
        "primary": "有弹性的；适应力强的",
        "pos_groups": [
            ("adj.", ["有弹性的", "能复原的", "适应力强的", "弹回的"]),
            ("n.", ["弹性", "弹力"]),
        ],
        "sentence_en": "The team proved remarkably resilient under pressure.",
        "sentence_cn": "该团队在压力下表现出非凡的适应力。",
        "spans_en": [(27, 36)], "spans_cn": [(13, 16)],
    },
    {
        "word": "question", "phonetic": "ˈkwestʃən",
        "primary": "问题；疑问",
        "pos_groups": [
            ("n.", ["问题", "疑问", "难题", "询问", "议题", "考题"]),
            ("v.", ["询问", "质疑", "怀疑", "审问", "盘问"]),
        ],
        "sentence_en": "That is not the question we should be asking.",
        "sentence_cn": "那不是我们应该问的问题。",
        "spans_en": [(16, 24)], "spans_cn": [(9, 11)],
    },
]


def main():
    theme = "dark" if "dark" in sys.argv else "light"
    cfg = cfg_mod.load()
    cfg["theme"] = theme

    root = tk.Tk()
    root.withdraw()
    try:
        dpi = ctypes.windll.user32.GetDpiForWindow(root.winfo_id())
        if dpi:
            root.tk.call("tk", "scaling", dpi / 72.0)
    except Exception:
        pass

    backdrop = tk.Toplevel(root)
    backdrop.overrideredirect(True)
    backdrop.attributes("-topmost", True)
    backdrop.configure(bg="#0f0f10" if theme == "dark" else "#f4f4f5")
    backdrop.geometry("1000x760+90+60")

    popup = Popup(root, cfg, on_speak=tts.speak)
    anchor = (240, 190)
    idx = [0]

    def render():
        popup.show(anchor, SAMPLES[idx[0] % len(SAMPLES)])

    def nxt(_=None):
        idx[0] += 1
        render()

    def close(_=None):
        root.destroy()

    render()
    popup.card.bind("<Double-Button-1>", nxt)
    root.bind_all("<Escape>", close)
    root.bind_all("<Button-3>", close)

    def shot():
        try:
            import mss
            import mss.tools
            backdrop.lift()
            popup.win.lift()
            popup.win.update_idletasks()
            g = popup.win.geometry()
            size = g.split("+")[0]
            x, y = int(g.split("+")[1]), int(g.split("+")[2])
            w, h = (int(v) for v in size.split("x"))
            m = (getattr(mss, "MSS", None) or mss.mss)()
            im = m.grab({"left": x - 16, "top": y - 16,
                         "width": w + 32, "height": h + 32})
            mss.tools.to_png(im.rgb, im.size, output="demo.png")
            print("已保存 demo.png")
        except Exception as e:  # noqa: BLE001
            print("截图失败:", e)

    root.after(500, shot)
    root.after(60000, close)
    root.mainloop()


if __name__ == "__main__":
    main()
