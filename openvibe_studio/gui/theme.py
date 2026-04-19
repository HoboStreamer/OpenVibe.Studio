from __future__ import annotations

import ttkbootstrap as tb
import tkinter as tk


def apply_theme(root: tk.Tk) -> None:
    style = tb.Style(theme="darkly")
    root.configure(bg=style.colors.bg)
