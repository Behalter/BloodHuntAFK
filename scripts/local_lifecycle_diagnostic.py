"""Two-match autonomous diagnostic confined to its own local Tk fixture.

Close the game. Explicitly arm once. Actual local F events drive synthetic
Rune state; local button clicks drive fixture navigation. No game capture,
game window lookup, game navigation, or live game controller.
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
    root.title("Local two-match lifecycle diagnostic")
    root.geometry("620x360")
    status = tk.StringVar(value="Close the game. Click Run once to begin.")
    display = tk.StringVar(value="Not started")
    tk.Label(root, text="Local two-match lifecycle", font=("Segoe UI", 16)).pack(pady=12)
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
             "pending": None, "events": [], "cooldown_ticks": 0,
             "match": 1, "menu": None, "menu_index": 0, "click_pending": None}
    sent, received, acknowledged = [], [], []
    navigation = []
    # Fixture labels include stale results and summary observations.
    menu_schedule = ["final_summary", "final_summary", "match_found",
                     "results", "final_summary", "unknown", "map_loading",
                     "hero_selection", "hero_selection"]
    start = 0.0

    def focused():
        hwnd = user32.GetAncestor(root.winfo_id(), 2)
        return bool(hwnd and hwnd == user32.GetForegroundWindow())

    def report(message):
        status.set(message)
        print(message, flush=True)

    def finish(message):
        state["running"] = False
        menu_button.config(state="disabled")
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

    def menu_clicked():
        if not state["running"] or state["click_pending"] is None:
            return
        action = state["click_pending"]
        navigation.append(action)
        state["click_pending"] = None
        menu_button.config(state="disabled")
        root.focus_set()
        print(f"Local navigation acknowledged: {action}", flush=True)

    def menu_tick():
        nonlocal monitor, preview, audit
        if state["click_pending"] is not None:
            finish("FAIL: missing local button acknowledgement; no retry.")
            return
        i = state["menu_index"]
        if i == len(menu_schedule):
            if navigation != ["next fixture match", "confirm fixture"]:
                finish(f"FAIL: navigation sequence {navigation!r}")
                return
            state.update(match=2, index=0, rune=Rune.READY, menu=None,
                         cooldown_ticks=0, events=[])
            monitor = ShadowMonitor(None, detector=lambda d, _: d)
            preview = WaveActionPreview()
            audit = AcknowledgementSimulation()
            print("Fixture match 2 started.", flush=True)
            root.after(500, tick)
            return
        label = menu_schedule[i]
        display.set(f"Between matches | {label}")
        action = {1: "next fixture match", 8: "confirm fixture"}.get(i)
        if action:
            menu_button.config(text=action, state="normal")
            root.update_idletasks()
            x = menu_button.winfo_rootx() + menu_button.winfo_width() // 2
            y = menu_button.winfo_rooty() + menu_button.winfo_height() // 2
            if not focused() or root.winfo_containing(x, y) != menu_button:
                finish("ABORTED: local button is not the foreground target.")
                return
            state["click_pending"] = action
            try:
                inputs.click(x, y)
            except Exception as exc:
                finish(f"ERROR: local click: {exc}; no retry.")
                return
        state["menu_index"] += 1
        root.after(500, tick)

    def tick():
        if not state["running"]:
            return
        if not focused():
            focus_check()
            return
        if state["pending"] is not None:
            finish("FAIL: missing local key acknowledgement; no retry.")
            return
        if state["menu"] is not None:
            menu_tick()
            return
        index = state["index"]
        if index == len(schedule):
            target = expected * state["match"]
            if sent != target or received != target or acknowledged != target:
                finish(f"FAIL: sent={sent}, received={received}, acknowledged={acknowledged}")
                return
            print(f"Fixture match {state['match']} complete: 9 acknowledgements.", flush=True)
            if state["match"] == 1:
                state["menu"] = True
                root.after(500, tick)
            elif navigation == ["next fixture match", "confirm fixture"]:
                finish("PASS: 2 fixture matches, 18 local key pairs, 18 state acknowledgements, 2 local button acknowledgements.")
            else:
                finish("FAIL: incorrect navigation sequence.")
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
        display.set(f"Match {state['match']} | {index + 1}/{len(schedule)} | {phase.value} | {rune.value}")
        if proposal is not None:
            if (len(sent) >= len(expected) * state["match"] or proposal.intent != expected[len(sent) % len(expected)]
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
        report("Running two local fixtures. Leave focus here; do not touch keyboard or mouse.")
        root.after(350, tick)

    root.bind("<KeyPress>", lambda e: record(e, "down"))
    root.bind("<KeyRelease>", lambda e: record(e, "up"))
    root.bind("<Escape>", lambda e: stop())
    root.bind("<FocusOut>", lambda e: root.after_idle(focus_check))
    button = tk.Button(root, text="Run once", command=arm)
    button.pack(pady=8)
    menu_button = tk.Button(root, text="Fixture navigation", state="disabled", command=menu_clicked)
    menu_button.pack(pady=8)
    tk.Button(root, text="Stop (Esc)", command=stop).pack()
    tk.Button(root, text="Close", command=root.destroy).pack(pady=6)
    print("Two local synthetic matches only. Close the game before testing.", flush=True)
    root.mainloop()


if __name__ == "__main__":
    main()
