"""Bounded, supervised single-match Rune test for an authorized environment.

No mouse input, matchmaking, healing, inventory routines, refocusing, or
retries. Operator starts the match and handles menus. F8/F10 stop permanently.
After combat input is disabled, observe closeout read-only for up to 60 seconds;
never rearm in the same process.
Requires explicit opt-in; never use in an unauthorized game environment.
"""
import argparse
import csv
from dataclasses import asdict, replace
from pathlib import Path
import time


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorized-test", action="store_true",
                        help="Confirm explicit permission for this test environment")
    parser.add_argument("--wave-reference", required=True, type=Path)
    parser.add_argument("--screen-reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if not args.authorized_test:
        parser.error("Explicit authorization is required; no input sent.")
    if args.output.exists():
        parser.error("Choose a new output directory.")
    if not all(p.is_file() for p in (args.wave_reference, args.screen_reference)):
        parser.error("Reference recordings must exist.")

    from bloodhunt import inputs, vision, winapi, settings
    from bloodhunt.wave_state import Phase, Rune
    from scripts.analyze_video import Calibration, detect, normalize
    from scripts.post_match_detector import PostMatchDetector
    from scripts.lifecycle_timeline import TimelineRow, combine
    from scripts.shadow_monitor import ShadowMonitor
    from scripts.wave_action_preview import WaveActionPreview

    if not settings.GAME_TITLE or not settings.GAME_CLASS:
        parser.error("Explicit game title and class are required.")
    if settings.ABILITY_KEY.lower() != "f":
        parser.error("This test requires the calibrated F binding.")
    wave = Calibration.from_video(args.wave_reference, 55., 80., 285., 56., 255., 260.)
    post = PostMatchDetector.from_recording(args.screen_reference)
    monitor = ShadowMonitor(None, detector=lambda d, _: d)
    preview = WaveActionPreview()
    args.output.mkdir(parents=True, exist_ok=False)

    def stop_requested():
        return any(winapi.user32.GetAsyncKeyState(vk) & 0x8000
                   for vk in (0x77, 0x79))

    def wait(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if stop_requested():
                return False
            time.sleep(min(0.05, max(0, end - time.monotonic())))
        return not stop_requested()

    print("Authorized supervised test only. F8/F10 stop; Alt+Tab aborts after focus lock.")
    print("Switch to the authorized game window within 10 seconds. Start the match manually.")
    print("The test arms only after two preparation/ready observations.")
    print("Handle shop selections manually; do not press F while armed.")
    print("After victory, advance with Space manually; stop at ONE MORE ROUND.", flush=True)
    if not wait(10):
        print("Stopped before arming. No input sent.")
        return
    hwnd = winapi.user32.GetForegroundWindow()
    if not hwnd or not winapi.is_game(hwnd):
        print("ABORTED: authorized game window not foreground. No input sent.")
        return

    def foreground():
        return (winapi.user32.GetForegroundWindow() == hwnd and winapi.is_game(hwnd))

    screen = vision.Screen()
    start = time.monotonic()
    armed = False
    prep_streak = 0
    pending = None
    last = None
    uncertain_since = None
    closeout_since = None
    closeout_previous = None
    summary_streak = 0
    victory_streak = 0
    victory_observed = False
    attempts = acknowledged = 0
    outcome = "ABORTED: time limit reached."
    try:
        with (args.output / "samples.csv").open("x", newline="", encoding="utf-8") as sf, \
             (args.output / "actions.csv").open("x", newline="", encoding="utf-8") as af:
            sw = csv.DictWriter(sf, fieldnames=tuple(TimelineRow.__dataclass_fields__))
            aw = csv.writer(af)
            sw.writeheader()
            aw.writerow(("seconds", "intent", "status", "details"))
            sf.flush()
            af.flush()

            def log(intent, status, details):
                now = time.monotonic() - start
                aw.writerow((f"{now:.3f}", intent, status, details))
                af.flush()
                print(f"{now:7.2f}s {status:<14} {intent} {details}", flush=True)

            while time.monotonic() - start < 600:
                tick = time.monotonic()
                now = tick - start
                if stop_requested() or not foreground():
                    outcome = "ABORTED: operator stop or focus loss."
                    break
                if not armed and now > 120:
                    outcome = "ABORTED: no stable preparation/ready state within 120 seconds."
                    break
                if last is not None and tick - last > 2.5:
                    outcome = "ABORTED: observation gap."
                    break
                last = tick
                area = winapi.game_area()
                screen.refresh()
                w, h = screen.size
                captured_area = (screen.mon["left"], screen.mon["top"], w, h)
                if (not area or winapi._game_hwnd != hwnd or tuple(area) != captured_area
                        or w <= 0 or h <= 0 or w * 9 != h * 16):
                    outcome = "ABORTED: invalid game capture geometry."
                    break
                frame = screen.grab()
                if (not foreground() or winapi.game_area() != area
                        or winapi._game_hwnd != hwnd or stop_requested()):
                    outcome = "ABORTED: focus, geometry, or stop changed during capture."
                    break
                image = normalize(frame)
                d = detect(image, wave)
                p = post.classify(image)
                row = combine(now, d.phase.value, d.rune.value, p.screen, p.markers)
                sw.writerow(asdict(row))
                sf.flush()

                if not armed:
                    prep_streak = prep_streak + 1 if (
                        row.screen == "preparation" and row.visible_rune == "ready") else 0
                    if prep_streak >= 2:
                        armed = True
                        log("", "armed", "stable preparation and ready; single match only")
                    else:
                        if not wait(max(0, 0.5 - (time.monotonic() - tick))):
                            outcome = "ABORTED: operator stop."
                            break
                        continue

                # Closeout is a one-way latch. No input path can be reached
                # after it is set, even if the combat HUD reappears.
                valid = row.screen in {"preparation", "combat"} and row.visible_rune != "unknown"
                if closeout_since is None:
                    reason = None
                    if (d.phase in (Phase.MATCH_ENDING, Phase.POST_MATCH)
                            or p.screen in {"victory_banner", "mvp", "progression", "results", "final_summary"}):
                        reason = "match ending/results evidence"
                    elif row.reason in {"classifier_disagreement", "unresolved_screen_markers"}:
                        outcome = "ABORTED: conflicting or unresolved screen evidence."
                        break
                    elif row.screen not in {"preparation", "combat", "unknown", "blessing_shop"}:
                        outcome = "ABORTED: unexpected lifecycle screen."
                        break
                    elif row.screen == "blessing_shop" or valid:
                        uncertain_since = None
                    elif uncertain_since is None:
                        uncertain_since = tick
                    elif tick - uncertain_since >= 3:
                        reason = "HUD uncertain for three seconds"
                    if reason is not None:
                        closeout_since = tick
                        log("", "input_disabled", reason + "; read-only closeout")
                        if pending is not None:
                            log(pending[0], "unacknowledged", "input disabled before acknowledgement")
                            pending = None

                if closeout_since is not None:
                    if row.screen != closeout_previous:
                        log("", "closeout", row.screen)
                        closeout_previous = row.screen
                    victory_frame = (row.screen == "victory_banner" or
                                     (row.screen in {"progression", "results", "final_summary"}
                                      and "victory_header" in p.markers))
                    victory_streak = victory_streak + 1 if victory_frame else 0
                    if victory_streak >= 2 and not victory_observed:
                        victory_observed = True
                        log("", "victory_seen", "two consecutive positive victory observations")
                    summary_frame = (row.screen == "final_summary"
                                     and "victory_header" in p.markers
                                     and "summary" in p.markers)
                    summary_streak = summary_streak + 1 if summary_frame else 0
                    if summary_streak >= 2 and victory_observed:
                        outcome = ("COMPLETE: victory and final summary observed; input disabled."
                                   if attempts == acknowledged else
                                   "COMPLETE: victory observed, but not all input attempts acknowledged.")
                        break
                    if row.screen in {"match_found", "map_loading", "hero_selection"}:
                        outcome = "STOPPED: subsequent match screen observed; no rearming."
                        break
                    if tick - closeout_since >= 60:
                        outcome = ("STOPPED: victory observed; final summary not confirmed."
                                   if victory_observed else
                                   "STOPPED: closeout timeout; victory not confirmed.")
                        break
                    if not wait(max(0, 0.5 - (time.monotonic() - tick))):
                        outcome = "ABORTED: operator stop."
                        break
                    continue

                # Mask overlays and uncertain frames before the existing advisor.
                masked = d if valid else replace(d, phase=Phase.UNKNOWN, rune=Rune.UNKNOWN)
                sample = monitor.feed(now, masked)
                proposals = preview.observe(sample)

                if pending is not None:
                    intent, phase, before, expected, deadline, streak = pending
                    if (time.monotonic() > deadline or row.screen == "blessing_shop"
                            or (valid and row.screen != phase)):
                        outcome = "ABORTED: acknowledgement timeout or phase/overlay change."
                        break
                    if valid and row.visible_rune in expected:
                        streak += 1
                    elif valid and row.visible_rune != before:
                        outcome = "ABORTED: contradictory Rune acknowledgement."
                        break
                    else:
                        streak = 0
                    if proposals:
                        outcome = "ABORTED: new proposal while acknowledgement pending."
                        break
                    if streak >= 2:
                        acknowledged += 1
                        log(intent, "acknowledged", "two subsequent expected HUD observations")
                        pending = None
                    else:
                        pending = (intent, phase, before, expected, deadline, streak)
                elif proposals:
                    if len(proposals) != 1 or not valid or attempts >= 12:
                        outcome = "ABORTED: ambiguous proposal or action limit."
                        break
                    proposal = proposals[0]
                    spec = {
                        "activate": ("combat", "ready", {"active"}),
                        "long_wave_activate": ("combat", "ready", {"active"}),
                        "cancel": ("preparation", "active", {"cooldown", "ready"}),
                    }.get(proposal.intent)
                    if (spec is None or (row.screen, row.visible_rune) != spec[:2]
                            or sample.confirmed_phase.value != spec[0]):
                        outcome = "ABORTED: proposal does not match current HUD."
                        break
                    if (not foreground() or stop_requested() or winapi.game_area() != area
                            or winapi._game_hwnd != hwnd or time.monotonic() - tick > 0.75
                            or winapi.user32.GetAsyncKeyState(0x46) & 0x8000):
                        outcome = "ABORTED: input preflight failed."
                        break
                    attempts += 1
                    log(proposal.intent, "attempt", "one F tap; delivery not yet acknowledged")
                    if not foreground() or stop_requested():
                        outcome = "ABORTED: stop or focus loss before dispatch."
                        break
                    inputs.press("f")
                    pending = (proposal.intent, spec[0], spec[1], spec[2],
                               time.monotonic() + 3, 0)

                if not wait(max(0, 0.5 - (time.monotonic() - tick))):
                    outcome = "ABORTED: operator stop."
                    break

            if pending is not None:
                log(pending[0], "unacknowledged", outcome)
            log("", "terminated", outcome)
    except KeyboardInterrupt:
        outcome = "ABORTED: Ctrl+C."
    except Exception as exc:
        outcome = f"ABORTED: {type(exc).__name__}: {exc}"
    finally:
        screen.sct.close()
        print(outcome, flush=True)
        print(f"Attempts: {attempts}; acknowledged: {acknowledged}; reports: {args.output}", flush=True)


if __name__ == "__main__":
    main()
