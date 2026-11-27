"""Wave-aware runtime for the original BloodHuntAFK GUI and run command.

Derived from the successful supervised two-match build. Retains its visual
gates and per-match action limits; session duration uses existing MAX_HOURS.
The original timed runtime is untouched. Explicit authorization required.
"""
import csv
from dataclasses import asdict, replace
from pathlib import Path
import time
from math import isfinite


def run(profile, refit, keys, status, start_delay):
    from bloodhunt import settings
    from bloodhunt.common import DEBUG, HERE, stamp, log as app_log
    from types import SimpleNamespace

    if not getattr(settings, "WAVE_AUTHORIZED_TEST", False):
        raise SystemExit("Wave-aware mode requires WAVE_AUTHORIZED_TEST in an authorized environment.")
    def reference(name):
        value = getattr(settings, name, "")
        if not value:
            raise SystemExit(f"Set {name} to the calibrated reference recording.")
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = HERE / path
        if not path.is_file():
            raise SystemExit(f"Reference recording not found: {path}")
        return path
    args = SimpleNamespace(
        wave_reference=reference("WAVE_REFERENCE"),
        screen_reference=reference("WAVE_SCREEN_REFERENCE"),
        output=DEBUG / ("wave_session_" + stamp()),
    )
    def fail(message):
        raise SystemExit(message)
    if not isfinite(settings.MAX_HOURS) or settings.MAX_HOURS < 0:
        fail("MAX_HOURS must be finite and nonnegative.")
    if not isfinite(settings.HEAL_EVERY) or not isfinite(settings.HEAL_DELAY_POST_F):
        fail("Healing settings must be finite.")
    if settings.HEAL_EVERY < 0 or settings.HEAL_DELAY_POST_F < 0:
        fail("Healing settings must be nonnegative.")
    from bloodhunt import inputs, vision, winapi, settings
    import cv2
    import numpy as np
    from bloodhunt.wave_state import Phase, Rune
    from scripts.analyze_video import Calibration, detect, normalize
    from scripts.post_match_detector import PostMatchDetector
    from scripts.lifecycle_timeline import TimelineRow, combine
    from scripts.shadow_monitor import ShadowMonitor
    from scripts.wave_action_preview import WaveActionPreview

    if not settings.GAME_TITLE or not settings.GAME_CLASS:
        fail("Explicit game title and class are required.")
    if settings.ABILITY_KEY.lower() != "f":
        fail("This test requires the calibrated F binding.")
    wave = Calibration.from_video(args.wave_reference, 55., 80., 285., 56., 255., 260.)
    post = PostMatchDetector.from_recording(args.screen_reference)
    monitor = ShadowMonitor(None, detector=lambda d, _: d)
    preview = WaveActionPreview()

    # Hero confirmation uses the user's recorded hero-selection screen.
    # The name and button are separate fixed crops; the mode is checked
    # independently by PostMatchDetector. CANCEL proves the button changed.
    boxes = {"thor": (40, 665, 170, 720),
             "confirm": (1638, 715, 1732, 744),
             "cancel": (1638, 715, 1732, 744)}
    def crop(image, name):
        x, y, x2, y2 = boxes[name]
        return cv2.cvtColor(image[y:y2, x:x2], cv2.COLOR_BGR2GRAY)
    hero_refs = {}
    cap = cv2.VideoCapture(str(args.screen_reference))
    try:
        for name, seconds in (("thor", 61), ("confirm", 61), ("cancel", 65)):
            if not cap.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000):
                fail("Cannot seek hero reference.")
            ok, image = cap.read()
            if not ok or image.shape != (1080, 1920, 3):
                fail("Cannot read 1920x1080 hero reference.")
            hero_refs[name] = crop(image, name)
            if float(hero_refs[name].std()) < 8:
                fail("Invalid hero reference contrast.")
    finally:
        cap.release()
    def hero_score(image, name):
        value = float(cv2.matchTemplate(crop(image, name), hero_refs[name],
                                        cv2.TM_CCOEFF_NORMED)[0, 0])
        return value if np.isfinite(value) else -1.
    # Use the original selected profile and its scaled templates.
    base_profile = profile
    profile = None
    nav_templates = {}

    args.output.mkdir(parents=True, exist_ok=False)

    def stop_requested():
        keys.poll()
        return keys.quit

    def wait(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if stop_requested():
                return False
            if keys.paused:
                return True  # return to the loop; never dispatch while paused
            time.sleep(min(0.05, max(0, end - time.monotonic())))
        return not stop_requested()

    status.started = time.monotonic()
    status.next_f = None
    def time_limit():
        return bool(settings.MAX_HOURS and
                    time.monotonic() - status.started >= settings.MAX_HOURS * 3600)
    app_log("Wave-aware mode: manual first match; automatic replay; original MAX_HOURS applies.")
    app_log("Shop choices remain manual. Gear routines and auto-refocus are disabled in wave mode.")
    app_log("Pause before arming can resume. Pause/focus loss after arming stops the session safely.")
    app_log(f"Wave reports: {args.output}")
    if start_delay and not wait(start_delay):
        status.state = "stopped"
        return
    status.state = "waiting for game foreground"
    while not stop_requested() and not time_limit():
        if not keys.paused and winapi.game_in_front():
            hwnd = winapi.user32.GetForegroundWindow()
            if hwnd and winapi.is_game(hwnd):
                break
        time.sleep(0.1)
    else:
        status.state = "stopped"
        return

    def foreground():
        return (winapi.user32.GetForegroundWindow() == hwnd and winapi.is_game(hwnd))

    screen = vision.Screen()
    start = time.monotonic()
    status.profile = str(base_profile)
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
    confirmed_cancels = 0
    terminal_interruption = False
    last_nav_report = -100.
    total_attempts = total_acknowledged = 0
    match = 1
    completed = 0
    waiting_next = False
    next_since = None
    replay_seen = False
    hero_verified = False
    hero_attempted = False
    hero_streak = 0
    cancel_streak = 0
    nav_candidate = None
    nav_streak = 0
    skip_count = 0
    next_nav_at = 0.
    cooldown_since = None
    last_heal = None
    outcome = "STOPPED: MAX_HOURS reached."
    try:
        with (args.output / "samples.csv").open("x", newline="", encoding="utf-8") as sf, \
             (args.output / "actions.csv").open("x", newline="", encoding="utf-8") as af:
            sw = csv.DictWriter(sf, fieldnames=("match", *TimelineRow.__dataclass_fields__))
            aw = csv.writer(af)
            sw.writeheader()
            aw.writerow(("seconds", "match", "intent", "status", "details"))
            sf.flush()
            af.flush()

            def log(intent, status, details):
                now = time.monotonic() - start
                aw.writerow((f"{now:.3f}", match, intent, status, details))
                af.flush()
                app_log(f"{now:7.2f}s M{match} {status:<14} {intent} {details}")

            while not time_limit():
                tick = time.monotonic()
                now = tick - start
                if stop_requested():
                    outcome = "ABORTED: operator stop."
                    break
                if keys.paused:
                    if armed or waiting_next:
                        outcome = "STOPPED: paused after arming; restart at a fresh match."
                        break
                    status.state = "paused before arming"
                    while keys.paused and not stop_requested() and not time_limit():
                        time.sleep(0.1)
                    start = time.monotonic()
                    last = None
                    prep_streak = 0
                    continue
                if not foreground():
                    outcome = "ABORTED: focus loss."
                    break
                if not armed and not waiting_next and now > 120:
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
                        or winapi._game_hwnd != hwnd or stop_requested() or keys.paused):
                    outcome = "ABORTED: focus, geometry, or stop changed during capture."
                    break
                if profile is None or profile.screen != (w, h):
                    profile = refit((w, h))
                    status.profile = str(profile)
                    nav_templates = {t.name.lower(): t for t in profile.templates()
                                     if t.name.lower() in {"click_skip", "click_one_more_round",
                                                           "routine_storage_full"}}
                    if set(nav_templates) != {"click_skip", "click_one_more_round", "routine_storage_full"}:
                        outcome = "ABORTED: required original profile templates missing."
                        break
                    if not all(t.locked for t in nav_templates.values()):
                        outcome = "ABORTED: original templates must be position locked."
                        break
                image = normalize(frame)
                d = detect(image, wave)
                p = post.classify(image)
                row = combine(now, d.phase.value, d.rune.value, p.screen, p.markers)
                sw.writerow({"match": match, **asdict(row)})
                sf.flush()
                status.state = f"wave mode: match {match} / {row.screen} / Rune {row.visible_rune}"

                def safe_input():
                    return (foreground() and not stop_requested() and not keys.paused
                            and not time_limit() and winapi.game_area() == area and winapi._game_hwnd == hwnd
                            and time.monotonic() - tick <= 0.75)

                def click_local(point):
                    if point is None or not (0 <= point[0] < w and 0 <= point[1] < h):
                        return False
                    if not safe_input() or winapi.mouse_down():
                        return False
                    inputs.click(*screen.to_screen(point))
                    return True

                # Only after the first replay click. No F or other navigation
                # while waiting for the next match; only a verified Thor CONFIRM.
                if waiting_next:
                    if tick - next_since >= 120:
                        outcome = "STOPPED: replay/hero/preparation not confirmed within 120 seconds."
                        break
                    if row.screen in {"match_found", "map_loading", "hero_selection"}:
                        if not replay_seen:
                            log("replay", "acknowledged", row.screen)
                        replay_seen = True
                    if vision.best(vision.shrink(frame), [nav_templates["routine_storage_full"]]):
                        outcome = "STOPPED: storage full; no gear changes."
                        break
                    if row.screen == "hero_selection":
                        thor = hero_score(image, "thor") >= 0.90
                        confirm = hero_score(image, "confirm") >= 0.90
                        cancel = hero_score(image, "cancel") >= 0.90
                        hero_streak = hero_streak + 1 if thor and confirm and not cancel else 0
                        cancel_streak = cancel_streak + 1 if thor and cancel and not confirm else 0
                        if hero_streak >= 2 and not hero_attempted:
                            # The tight crop was measured at 1920x1080; click its centre.
                            point = (round(1685 * w / 1920), round(729 * h / 1080))
                            log("confirm_thor", "attempt", "Thor + Nightmare 1 + CONFIRM")
                            if not click_local(point):
                                outcome = "ABORTED: hero confirmation preflight failed."
                                break
                            hero_attempted = True
                            status.stats["click_confirm_thor"] += 1
                        if cancel_streak >= 2 and not hero_verified:
                            hero_verified = True
                            log("confirm_thor", "acknowledged", "Thor + CANCEL observed")
                    else:
                        hero_streak = cancel_streak = 0
                    prep_streak = prep_streak + 1 if (
                        replay_seen and hero_verified and row.screen == "preparation"
                        and row.visible_rune == "ready") else 0
                    if prep_streak >= 2:
                        match += 1
                        waiting_next = False
                        armed = True
                        monitor = ShadowMonitor(None, detector=lambda d, _: d)
                        preview = WaveActionPreview()
                        pending = None
                        uncertain_since = closeout_since = closeout_previous = None
                        summary_streak = victory_streak = 0
                        victory_observed = False
                        attempts = acknowledged = skip_count = nav_streak = 0
                        confirmed_cancels = 0
                        terminal_interruption = False
                        last_nav_report = -100.
                        nav_candidate = None
                        next_nav_at = 0.
                        cooldown_since = last_heal = None
                        status.stats["matches"] += 1
                        log("", "armed", "fresh Rune controller")
                    else:
                        if not wait(max(0, 0.5 - (time.monotonic() - tick))):
                            outcome = "ABORTED: operator stop."
                            break
                        continue

                if not armed:
                    prep_streak = prep_streak + 1 if (
                        row.screen == "preparation" and row.visible_rune == "ready") else 0
                    if prep_streak >= 2:
                        armed = True
                        status.stats["matches"] += 1
                        log("", "armed", "stable preparation and ready; first match")
                    else:
                        if not wait(max(0, 0.5 - (time.monotonic() - tick))):
                            outcome = "ABORTED: operator stop."
                            break
                        continue

                # Closeout permanently disables Rune input for this match.
                # Menu input still requires independently confirmed victory.
                valid = row.screen in {"preparation", "combat"} and row.visible_rune != "unknown"
                terminal_candidate = (
                    pending is not None and pending[0] == "activate"
                    and pending[1] == "combat" and confirmed_cancels == 4
                    and attempts == acknowledged + 1
                )
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
                    # A fast boss kill can remove the HUD before the final
                    # activation is acknowledged. Timeout may precede the
                    # three-second uncertainty timer; latch off F now, not
                    # terminate observation. Never grant a fake acknowledgement.
                    if (reason is None and terminal_candidate
                            and time.monotonic() > pending[4]
                            and row.screen == "unknown"
                            and row.reason == "no_positive_classification"):
                        reason = "final activation timeout with HUD absent"
                    if reason is not None:
                        closeout_since = tick
                        log("", "input_disabled", reason + "; Rune input latched off")
                        if pending is not None:
                            terminal_interruption = terminal_candidate
                            log(pending[0], "unacknowledged",
                                "possible terminal interruption; victory required"
                                if terminal_interruption else
                                "input disabled before acknowledgement")
                            pending = None

                if closeout_since is not None:
                    if row.screen != closeout_previous:
                        log("", "closeout", f"{row.screen}; phase={row.raw_phase}; markers={row.markers}; {row.reason}")
                        closeout_previous = row.screen
                    if row.screen in {"preparation", "combat", "blessing_shop"}:
                        outcome = "STOPPED: gameplay returned after Rune input was disabled."
                        break
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
                    if row.screen in {"match_found", "map_loading", "hero_selection"}:
                        outcome = "STOPPED: unexpected next-match screen before replay."
                        break
                    if tick - closeout_since >= 90:
                        outcome = "STOPPED: closeout timeout; no further input."
                        break

                    small = vision.shrink(frame)
                    if vision.best(small, [nav_templates["routine_storage_full"]]):
                        outcome = "STOPPED: storage full; no gear changes."
                        break
                    replay_hit = vision.best(small, [nav_templates["click_one_more_round"]],
                                             skip_dimmed=True)
                    skip_hit = vision.best(small, [nav_templates["click_skip"]],
                                           skip_dimmed=True)
                    if tick - last_nav_report >= 5:
                        scores = []
                        for name in ("click_skip", "click_one_more_round"):
                            t = nav_templates[name]
                            score, _, contrast = vision.find(small, t)
                            scores.append(f"{name}={score:.3f}/{vision.threshold(t):.3f}, contrast={contrast:.2f}")
                        log("", "nav_evidence", f"victory={victory_observed}; " + "; ".join(scores))
                        last_nav_report = tick
                    # Replay requires BOTH the independent summary classifier and
                    # the original active yellow button.
                    if summary_streak >= 2 and victory_observed and replay_hit:
                        all_confirmed = attempts > 0 and attempts == acknowledged
                        final_interrupted = terminal_interruption and attempts == acknowledged + 1
                        if not (all_confirmed or final_interrupted):
                            outcome = "STOPPED: victory observed but nonterminal Rune attempt unacknowledged."
                            break
                        completed += 1
                        status.stats["victories"] += 1
                        log("", "match_complete",
                            "victory and final summary confirmed; final Rune unacknowledged"
                            if final_interrupted else "victory and final summary confirmed")
                        t, score, pos = replay_hit
                        point = vision.click_point(t, pos, profile.click_at)
                        log("replay", "attempt", f"original template score={score:.3f}")
                        if not click_local(point):
                            outcome = "ABORTED: replay preflight failed."
                            break
                        status.stats["click_one_more_round"] += 1
                        waiting_next = True
                        next_since = time.monotonic()
                        replay_seen = hero_verified = hero_attempted = False
                        hero_streak = cancel_streak = prep_streak = 0
                        continue

                    # SPACE is the original skip template, not a blind timer.
                    # Unknown frames may be an MVP animation; require prior
                    # positive victory, no conflicting evidence, no final button,
                    # and never use SPACE on a known gameplay/hero screen.
                    eligible = (victory_observed and not replay_hit and skip_hit
                                and row.screen in {"victory_banner", "mvp", "progression", "results", "unknown"}
                                and row.reason not in {"classifier_disagreement", "unresolved_screen_markers"}
                                and d.phase not in {Phase.PREPARATION, Phase.COMBAT})
                    candidate = "space" if eligible else None
                    nav_streak = nav_streak + 1 if candidate and candidate == nav_candidate else int(bool(candidate))
                    nav_candidate = candidate
                    if nav_streak >= 2 and tick >= next_nav_at:
                        if skip_count >= 5:
                            outcome = "STOPPED: bounded SPACE advancement limit."
                            break
                        if not safe_input() or winapi.user32.GetAsyncKeyState(0x20) & 0x8000:
                            outcome = "ABORTED: SPACE preflight failed."
                            break
                        log("space", "attempt", f"original SPACE template score={skip_hit[1]:.3f}")
                        if not safe_input():
                            outcome = "ABORTED: focus/stop changed before SPACE."
                            break
                        inputs.press("space")
                        status.stats["click_skip"] += 1
                        skip_count += 1
                        nav_streak = 0
                        next_nav_at = time.monotonic() + 3.

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
                        total_acknowledged += 1
                        status.stats["Rune acknowledgements"] += 1
                        if intent == "cancel":
                            confirmed_cancels += 1
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
                    if (not safe_input()
                            or winapi.user32.GetAsyncKeyState(0x46) & 0x8000):
                        outcome = "ABORTED: input preflight failed."
                        break
                    attempts += 1
                    total_attempts += 1
                    log(proposal.intent, "attempt", "one F tap; delivery not yet acknowledged")
                    if not safe_input():
                        outcome = "ABORTED: stop or focus loss before dispatch."
                        break
                    inputs.press("f")
                    status.stats["F presses"] += 1
                    pending = (proposal.intent, spec[0], spec[1], spec[2],
                               time.monotonic() + 3, 0)

                # Optional healing, off by default. Only on observed combat
                # cooldown, never during preparation, pending F, or overlays.
                heal_eligible = (valid and row.screen == "combat"
                                 and row.visible_rune == "cooldown"
                                 and sample.confirmed_phase is Phase.COMBAT
                                 and pending is None and not proposals)
                if not heal_eligible:
                    cooldown_since = last_heal = None
                elif cooldown_since is None:
                    cooldown_since = tick
                elif (getattr(settings, "WAVE_HEAL", False)
                      and settings.HEAL_EVERY > 0
                      and tick - cooldown_since >= settings.HEAL_DELAY_POST_F
                      and (last_heal is None or tick - last_heal >= settings.HEAL_EVERY)):
                    vk = winapi.NAME_VKS.get(settings.HEAL_KEY.lower())
                    if (vk is None or vk in {0x46, 0x20, settings.PAUSE_KEY, settings.QUIT_KEY}
                            or not safe_input() or winapi.user32.GetAsyncKeyState(vk) & 0x8000):
                        outcome = "ABORTED: healing preflight failed."
                        break
                    inputs.press(settings.HEAL_KEY)
                    status.stats["X presses"] += 1
                    last_heal = time.monotonic()
                    log("heal", "attempt", "observed combat cooldown; not HUD acknowledged")

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
        status.state, status.next_f = "stopped", None
        app_log(outcome)
        app_log(f"Matches completed: {completed}; Rune attempts: {total_attempts}; acknowledged: {total_acknowledged}; reports: {args.output}")
