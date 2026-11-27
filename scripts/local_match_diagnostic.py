"""Exercise the existing preview pipeline in a synthetic local Tk window.

No game capture, game window lookup, navigation, or unattended game input.
Close the game first. One explicitly armed synthetic match per process.
The fixture supplies phase labels; actual local F events change its Rune.
"""
import ctypes
from ctypes import wintypes
import time
import tkinter as tk

from bloodhunt import inputs
from bloodhunt.wave_state import Phase, Rune
from scripts.analyze_video import Detection
from scripts.shadow_monitor import ShadowMonitor
from scripts.wave_action_preview import WaveActionPreview
from scripts.simulate_acknowledgement import AcknowledgementSimulation, Frame, Proposal


def main():
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
    user32.GetAncestor.restype = wintypes.HWND
    root = tk.Tk()
    root.title("Synthetic match - local input integration test")
    root.geometry("570x300")
    status = tk.StringVar(value="Close the game. Click Run once to begin.")
    display = tk.StringVar(value="Not started")
    tk.Label(root, text="Local synthetic match", font=("Segoe UI", 16)).pack(pady=12)
    tk.Label(root, textvariable=display, font=("Segoe UI", 13)).pack(pady=10)
    tk.Label(root, textvariable=status, wraplength=530).pack(pady=8)

    schedule = [Phase.PREPARATION] * 4 + [Phase.COMBAT] * 8
    for _ in range(4):
        schedule += [Phase.PREPARATION] * 8 + [Phase.COMBAT] * 8
    schedule += [Phase.MATCH_ENDING] * 2 + [Phase.UNKNOWN] * 2 + [Phase.POST_MATCH] * 4
    expected = ["activate"] + ["cancel", "activate"] * 4
    monitor = ShadowMonitor(None, detector=lambda d, _: d)
    preview = WaveActionPreview()
    audit = AcknowledgementSimulation()
    state = {"running": False, "index": 0, "rune": Rune.READY,
             "pending": None, "events": [], "cooldown_ticks": 0}
    sent, received, acknowledged = [], [], []
    start = 0.0

    def focused():
        hwnd = user32.GetAncestor(root.winfo_id(), 2)
        return bool(hwnd and hwnd == user32.GetForegroundWindow())

    def report(message):
        status.set(message)
        print(message, flush=True)

    def finish(message):
        state["running"] = False
        report(message)

    def stop():
        if state["running"]:
            finish("ABORTED: operator stop; no further input.")

    def focus_check():
        if state["running"] and not focused():
            finish("ABORTED: local window lost focus; no further input.")

    def record(event, kind):
        if not state["running"] or event.keysym.lower() != "f":
            return
        if state["pending"] is None:
            finish("FAIL: unexpected F event; no further input.")
            return
        state["events"].append(kind)
        if state["events"] == ["down", "up"]:
            intent = state["pending"]
            received.append(intent)
            state["pending"] = None
            state["rune"] = Rune.COOLDOWN if intent == "cancel" else Rune.ACTIVE
            state["cooldown_ticks"] = 3 if intent == "cancel" else 0
        elif state["events"] != ["down"]:
            finish("FAIL: unexpected key event sequence; no retry.")

    def tick():
        if not state["running"]:
            return
        if not focused():
            focus_check()
            return
        if state["pending"] is not None:
            finish("FAIL: missing local key acknowledgement; no retry.")
            return
        index = state["index"]
        if index == len(schedule):
            if sent == received == acknowledged == expected:
                finish("PASS: 9 local presses, 9 key pairs, 9 fixture state acknowledgements.")
            else:
                finish(f"FAIL: sent={sent}, received={received}, acknowledged={acknowledged}")
            return
        phase = schedule[index]
        rune = state["rune"]
        if phase not in (Phase.PREPARATION, Phase.COMBAT):
            rune = Rune.UNKNOWN
        now = time.monotonic() - start
        sample = monitor.feed(now, Detection(phase, rune, 0, 0, 0))
        proposals = preview.observe(sample)
        if len(proposals) > 1:
            finish("FAIL: multiple previews; no input.")
            return
        proposal = Proposal(proposals[0].intent) if proposals else None
        events = audit.observe(Frame(now, phase.value, sample.confirmed_phase.value,
                                     rune.value, focused=True), proposal)
        for event in events:
            if event.status == "acknowledged":
                acknowledged.append(event.intent)
                print(f"Fixture state acknowledged: {event.intent}", flush=True)
            elif event.status != "simulated":
                finish(f"FAIL: fixture audit {event.status}: {event.reason}")
                return
        display.set(f"Sample {index + 1}/{len(schedule)} | {phase.value} | {rune.value}")
        if proposal is not None:
            if (len(sent) >= len(expected) or proposal.intent != expected[len(sent)]
                    or not any(e.status == "simulated" for e in events)):
                finish("FAIL: unexpected preview; no input.")
                return
            if not focused():
                focus_check()
                return
            state["pending"] = proposal.intent
            state["events"] = []
            sent.append(proposal.intent)
            try:
                inputs.press("f")
            except Exception as exc:
                finish(f"ERROR: {exc}; no retry.")
                return
        if state["cooldown_ticks"]:
            state["cooldown_ticks"] -= 1
            if state["cooldown_ticks"] == 0:
                state["rune"] = Rune.READY
        state["index"] += 1
        root.after(500, tick)

    def arm():
        nonlocal start
        button.config(state="disabled")
        root.focus_set()
        state["running"] = True
        start = time.monotonic()
        report("Running once. Leave this window focused; do not press F.")
        root.after(350, tick)

    root.bind("<KeyPress>", lambda e: record(e, "down"))
    root.bind("<KeyRelease>", lambda e: record(e, "up"))
    root.bind("<Escape>", lambda e: stop())
    root.bind("<FocusOut>", lambda e: root.after_idle(focus_check))
    button = tk.Button(root, text="Run once", command=arm)
    button.pack(pady=8)
    tk.Button(root, text="Stop (Esc)", command=stop).pack()
    tk.Button(root, text="Close", command=root.destroy).pack(pady=6)
    print("Synthetic local match only. Close the game before testing.", flush=True)
    root.mainloop()


if __name__ == "__main__":
    main()
