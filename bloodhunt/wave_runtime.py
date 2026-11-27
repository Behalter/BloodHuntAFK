"""Wave-aware runtime for the original BloodHuntAFK GUI and run command.

Derived from the successful supervised two-match build. Retains its visual
gates and per-match action limits; session duration uses existing MAX_HOURS.
The original timed runtime is untouched. Explicit authorization required.
"""
import csv
from dataclasses import asdict, replace
import time
from math import isfinite


def run(profile, refit, keys, status, start_delay):
    from bloodhunt import settings
    from bloodhunt.common import DEBUG, HERE, stamp, log as app_log
    from types import SimpleNamespace

    if not getattr(settings, "WAVE_AUTHORIZED_TEST", False):
        raise SystemExit("Wave-aware mode requires WAVE_AUTHORIZED_TEST in an authorized environment.")
    args = SimpleNamespace(output=DEBUG / ("wave_session_" + stamp()))
    def fail(message):
        raise SystemExit(message)
    if not isfinite(settings.MAX_HOURS) or settings.MAX_HOURS < 0:
        fail("MAX_HOURS must be finite and nonnegative.")
    if not isfinite(settings.HEAL_EVERY) or not isfinite(settings.HEAL_DELAY_POST_F):
        fail("Healing settings must be finite.")
    if settings.HEAL_EVERY < 0 or settings.HEAL_DELAY_POST_F < 0:
        fail("Healing settings must be nonnegative.")
    from bloodhunt import inputs, vision, winapi, routines
    import cv2
    import numpy as np
    from bloodhunt.wave_state import Phase, Rune
    from scripts.analyze_video import detect, normalize
    from scripts.wave_templates import BUNDLE_RELATIVE, load_bundle, hero_crop
    from scripts.lifecycle_timeline import TimelineRow, combine
    from scripts.shadow_monitor import ShadowMonitor
    from scripts.wave_action_preview import WaveActionPreview
    from scripts.pause_recovery import ResumeGate, pending_reconciled

    if settings.PAUSE_KEY in {0x46, 0x20} or settings.QUIT_KEY in {0x46, 0x20} or settings.PAUSE_KEY == settings.QUIT_KEY:
        fail("Pause and Stop must be distinct from F and Space.")
    if not settings.GAME_TITLE or not settings.GAME_CLASS:
        fail("Explicit game title and class are required.")
    if settings.ABILITY_KEY.lower() != "f":
        fail("This test requires the calibrated F binding.")
    bundle = HERE / BUNDLE_RELATIVE
    if not bundle.is_file():
        fail(f"Missing recognition bundle: {bundle}. Run scripts.wave_templates once or install the packaged bundle.")
    try:
        wave, post, hero_refs = load_bundle(bundle)
    except Exception as exc:
        fail(f"Invalid recognition bundle: {bundle}: {exc}")
    app_log(f"Loaded 19 recognition templates from {bundle}")
    monitor = ShadowMonitor(None, detector=lambda d, _: d)
    preview = WaveActionPreview()

    def hero_score(image, name):
        value = float(cv2.matchTemplate(hero_crop(image, name), hero_refs[name],
                                        cv2.TM_CCOEFF_NORMED)[0, 0])
        return value if np.isfinite(value) else -1.
    # Use the original selected profile and its scaled templates.
    base_profile = profile
    profile = None
    nav_templates = {}
    stop_templates = []

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
    app_log(f"Shop choices remain manual. Guarded smelting: {bool(settings.RUN_ROUTINES)}; auto-refocus disabled.")
    app_log("F8 pauses input; resume waits for game focus and fresh recognition. Unpaused focus loss stops.")
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
    arm_since = start
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
    recovery = None
    recovery_since = None
    smelt_used = False
    storage_streak = 0
    replay_clicks = 0
    last_replay_at = None
    summary_verified = False
    launch_intent = "replay"
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
                    log("", "paused", "operator pause; no input")
                    while not stop_requested() and not time_limit():
                        status.state = "paused" if keys.paused else "resume: waiting for game focus"
                        if not keys.paused and foreground():
                            break
                        time.sleep(0.1)
                    else:
                        if keys.quit:
                            outcome = "ABORTED: operator stop."
                        break
                    resumed = time.monotonic()
                    # Discard pre-pause observation streaks, not action history.
                    last = None
                    prep_streak = hero_streak = cancel_streak = 0
                    summary_streak = victory_streak = nav_streak = storage_streak = 0
                    nav_candidate = closeout_previous = None
                    uncertain_since = cooldown_since = last_heal = None
                    arm_since = resumed
                    if waiting_next:
                        next_since = resumed
                    if closeout_since is not None:
                        closeout_since = resumed
                    next_nav_at = max(next_nav_at, resumed)
                    monitor = ShadowMonitor(None, detector=lambda d, _: d)
                    preview = WaveActionPreview()
                    recovery = ResumeGate() if armed and not waiting_next and closeout_since is None else None
                    recovery_since = resumed if recovery is not None else None
                    if pending is not None:
                        # The old acknowledgement clock is no longer meaningful.
                        pending = (*pending[:4], resumed + 30, 0)
                    log("", "resume", "fresh recognition; action counters and ending latch preserved")
                    continue
                if not foreground():
                    outcome = "ABORTED: focus loss."
                    break
                if not armed and not waiting_next and tick - arm_since > 120:
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
                if stop_requested():
                    outcome = "ABORTED: operator stop."
                    break
                if keys.paused:
                    continue  # discard captured frame and enter pause recovery
                if (not foreground() or winapi.game_area() != area
                        or winapi._game_hwnd != hwnd):
                    outcome = "ABORTED: focus or geometry changed during capture."
                    break
                if profile is None or profile.screen != (w, h):
                    profile = refit((w, h))
                    status.profile = str(profile)
                    templates = profile.templates()
                    stop_templates = [t for t in templates if t.kind == "stop"]
                    nav_templates = {t.name.lower(): t for t in templates
                                     if t.name.lower() in {"click_skip", "click_one_more_round",
                                                           "routine_storage_full"}}
                    if set(nav_templates) != {"click_skip", "click_one_more_round", "routine_storage_full"}:
                        outcome = "ABORTED: required original profile templates missing."
                        break
                    if not all(t.locked for t in nav_templates.values()):
                        outcome = "ABORTED: original templates must be position locked."
                        break
                if vision.best(vision.shrink(frame), stop_templates):
                    outcome = "STOPPED: original profile stop template recognized."
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

                def guarded_smelt():
                    # The storage warning is checked by the caller on fresh
                    # frames. The original sequence is not screen-verified
                    # step by step; stop on any interruption.
                    if not settings.RUN_ROUTINES or smelt_used:
                        return False
                    steps = profile.routines.get("storage_full")
                    if not steps or not safe_input():
                        return False
                    status.state = "running guarded storage-full routine"
                    log("storage_full", "attempt", "original profile sequence; rating=" + str(settings.SMELT_RATING))
                    def guard():
                        return (not stop_requested() and not keys.paused
                                and not time_limit() and foreground()
                                and winapi.game_area() == area and winapi._game_hwnd == hwnd)
                    if not routines.run_guarded("storage_full", steps, screen, guard):
                        return False
                    status.stats["storage_full routines"] += 1
                    log("storage_full", "sequence_done", "waiting for next-match recognition")
                    return True

                # Only after a verified replay or storage routine. No F
                # until the next match is positively recognized.
                if waiting_next:
                    if tick - next_since >= 120:
                        outcome = "STOPPED: replay/hero/preparation not confirmed within 120 seconds."
                        break
                    if row.screen in {"match_found", "map_loading", "hero_selection"}:
                        if not replay_seen:
                            log(launch_intent, "acknowledged", row.screen)
                        replay_seen = True
                    small = vision.shrink(frame)
                    storage_hit = vision.best(small, [nav_templates["routine_storage_full"]])
                    storage_streak = storage_streak + 1 if storage_hit else 0
                    if storage_hit:
                        if replay_seen or smelt_used or not settings.RUN_ROUTINES:
                            outcome = "STOPPED: storage warning after launch, repeat routine, or smelting disabled."
                            break
                        if storage_streak >= 2:
                            if not guarded_smelt():
                                outcome = "STOPPED: smelting interrupted or unavailable; inspect gear screen."
                                break
                            smelt_used = True
                            launch_intent = "storage_full"
                            last = None
                            next_since = time.monotonic()
                            storage_streak = 0
                        if not wait(max(0, 0.5 - (time.monotonic() - tick))):
                            outcome = "ABORTED: operator stop."
                            break
                        continue
                    # Backup retries retain the original configured interval
                    # and count, but a stuck replay alone cannot prove full
                    # storage. Do not start destructive menu actions on it.
                    if (not replay_seen and not smelt_used and settings.RUN_ROUTINES
                            and settings.BACKUP_ROUTINE_AFTER > 0
                            and row.screen == "final_summary"
                            and "victory_header" in p.markers and "summary" in p.markers
                            and last_replay_at is not None
                            and tick - last_replay_at >= settings.REPEAT_CLICK_AFTER):
                        retry = vision.best(small, [nav_templates["click_one_more_round"]], skip_dimmed=True)
                        if retry:
                            if replay_clicks >= settings.BACKUP_ROUTINE_AFTER:
                                outcome = "STOPPED: replay retry threshold reached without positive storage warning."
                                break
                            t, score, pos = retry
                            if not click_local(vision.click_point(t, pos, profile.click_at)):
                                if keys.paused and not keys.quit:
                                    continue
                                outcome = "ABORTED: replay retry preflight failed."
                                break
                            replay_clicks += 1
                            last_replay_at = time.monotonic()
                            status.stats["click_one_more_round"] += 1
                            log("replay", "retry", f"try {replay_clicks}; score={score:.3f}")
                            continue
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
                                if keys.paused and not keys.quit:
                                    continue
                                outcome = "ABORTED: hero confirmation preflight failed."
                                break
                            hero_attempted = True
                            status.stats["click_confirm_thor"] += 1
                        if cancel_streak >= 2 and hero_attempted and not hero_verified:
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
                        smelt_used = summary_verified = False
                        storage_streak = replay_clicks = 0
                        last_replay_at = None
                        launch_intent = "replay"
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
                    elif recovery is None and tick - uncertain_since >= 3:
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
                        recovery = recovery_since = None
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
                    if summary_streak >= 2 and victory_observed:
                        summary_verified = True
                    if row.screen in {"match_found", "map_loading", "hero_selection"}:
                        outcome = "STOPPED: unexpected next-match screen before replay."
                        break
                    if tick - closeout_since >= 90:
                        outcome = "STOPPED: closeout timeout; no further input."
                        break

                    small = vision.shrink(frame)
                    storage_hit = vision.best(small, [nav_templates["routine_storage_full"]])
                    storage_streak = storage_streak + 1 if storage_hit else 0
                    if storage_hit:
                        if not settings.RUN_ROUTINES or smelt_used:
                            outcome = "STOPPED: storage full; smelting disabled or already attempted."
                            break
                        if not summary_verified or not (attempts == acknowledged or
                                (terminal_interruption and attempts == acknowledged + 1)):
                            outcome = "STOPPED: storage warning without verified match closeout."
                            break
                        if storage_streak >= 2:
                            if not guarded_smelt():
                                outcome = "STOPPED: smelting interrupted or unavailable; inspect gear screen."
                                break
                            smelt_used = True
                            completed += 1
                            status.stats["victories"] += 1
                            log("", "match_complete", "victory and final summary confirmed before storage routine")
                            launch_intent = "storage_full"
                            waiting_next = True
                            next_since = time.monotonic()
                            replay_seen = hero_verified = hero_attempted = False
                            hero_streak = cancel_streak = prep_streak = storage_streak = 0
                            last = None
                        if not wait(max(0, 0.5 - (time.monotonic() - tick))):
                            outcome = "ABORTED: operator stop."
                            break
                        continue
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
                        t, score, pos = replay_hit
                        point = vision.click_point(t, pos, profile.click_at)
                        if not click_local(point):
                            if keys.paused and not keys.quit:
                                continue
                            outcome = "ABORTED: replay preflight failed."
                            break
                        completed += 1
                        status.stats["victories"] += 1
                        log("", "match_complete",
                            "victory and final summary confirmed; final Rune unacknowledged"
                            if final_interrupted else "victory and final summary confirmed")
                        log("replay", "attempt", f"original template score={score:.3f}")
                        status.stats["click_one_more_round"] += 1
                        replay_clicks = 1
                        last_replay_at = time.monotonic()
                        launch_intent = "replay"
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
                            if keys.paused and not keys.quit:
                                continue
                            outcome = "ABORTED: SPACE preflight failed."
                            break
                        log("space", "attempt", f"original SPACE template score={skip_hit[1]:.3f}")
                        if not safe_input():
                            if keys.paused and not keys.quit:
                                continue
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

                # Recover from current visible state, even within the same wave.
                # A pending tap is never repeated merely because it was paused.
                if recovery is not None:
                    if tick - recovery_since >= 30:
                        outcome = "STOPPED: resume state not verified within 30 seconds."
                        break
                    if not recovery.observe(row.screen, row.visible_rune):
                        status.state = "resume: verifying current phase and Rune"
                        if not wait(max(0, 0.5 - (time.monotonic() - tick))):
                            outcome = "ABORTED: operator stop."
                            break
                        continue
                    if pending is not None:
                        intent, phase, before, expected, deadline, streak = pending
                        if not pending_reconciled(row.screen, row.visible_rune, phase, expected):
                            outcome = "STOPPED: pre-pause Rune tap unresolved; no automatic retry."
                            break
                        acknowledged += 1
                        total_acknowledged += 1
                        status.stats["Rune acknowledgements"] += 1
                        if intent == "cancel":
                            confirmed_cancels += 1
                        log(intent, "reconciled", "three fresh expected HUD observations after pause; delivery causation unknown")
                        pending = None
                    log("", "recovered", f"{row.screen}/{row.visible_rune}; fresh advisor")
                    recovery = recovery_since = None
                    uncertain_since = None

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
                        if keys.paused and not keys.quit:
                            continue
                        outcome = "ABORTED: input preflight failed."
                        break
                    if not safe_input():
                        if keys.paused and not keys.quit:
                            continue
                        outcome = "ABORTED: stop or focus loss before dispatch."
                        break
                    inputs.press("f")
                    attempts += 1
                    total_attempts += 1
                    log(proposal.intent, "attempt", "one F tap; delivery not yet acknowledged")
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
                        if keys.paused and not keys.quit:
                            continue
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
        raise
    finally:
        screen.sct.close()
        status.state, status.next_f = "stopped", None
        app_log(outcome)
        app_log(f"Matches completed: {completed}; Rune attempts: {total_attempts}; acknowledged: {total_acknowledged}; reports: {args.output}")
