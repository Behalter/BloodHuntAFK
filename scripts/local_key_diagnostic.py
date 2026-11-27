"""One-shot keyboard delivery diagnostic for our own local Tk window.

Close the game before running. No game capture, navigation or control.
The user explicitly arms one test; no retries or background input.
"""
import ctypes
from ctypes import wintypes
import tkinter as tk

from bloodhunt import inputs


def main():
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND

    root = tk.Tk()
    root.title("Local keyboard delivery test")
    root.geometry("460x220")
    status = tk.StringVar(value="Click Run once, then leave this window focused.")
    tk.Label(root, text="Local F-key diagnostic", font=("Segoe UI", 15)).pack(pady=12)
    tk.Label(root, textvariable=status, wraplength=420).pack(pady=8)
    events = []
    state = {"armed": False, "sent": False}

    def own_window_focused():
        hwnd = user32.GetAncestor(root.winfo_id(), 2)
        return bool(hwnd and hwnd == user32.GetForegroundWindow())

    def record(event, kind):
        if state["sent"] and event.keysym.lower() == "f":
            events.append(kind)

    root.bind("<KeyPress>", lambda e: record(e, "down"))
    root.bind("<KeyRelease>", lambda e: record(e, "up"))

    def report(message):
        status.set(message)
        print(message, flush=True)

    def finish():
        state["sent"] = False
        if not own_window_focused():
            report("INCONCLUSIVE: focus changed during the test.")
        elif events == ["down", "up"]:
            report("PASS: one F key-down and one F key-up received.")
        else:
            report(f"FAIL: observed events {events!r}; no retry.")

    def send():
        if not own_window_focused():
            report("ABORTED: local test window is not foreground.")
            return
        state["sent"] = True
        try:
            inputs.press("f")
        except Exception as exc:
            state["sent"] = False
            report(f"ERROR: {exc}; no retry.")
            return
        root.after(600, finish)

    def arm():
        if state["armed"]:
            return
        state["armed"] = True
        button.config(state="disabled")
        root.focus_set()
        status.set("Testing once. Do not press keys or change focus.")
        root.after(350, send)

    button = tk.Button(root, text="Run once", command=arm)
    button.pack(pady=12)
    tk.Button(root, text="Close", command=root.destroy).pack()
    print("Local diagnostic only. Close the game before testing.", flush=True)
    root.mainloop()


if __name__ == "__main__":
    main()
