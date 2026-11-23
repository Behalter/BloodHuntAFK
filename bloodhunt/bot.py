"""The farming loop (`run`)."""
import sys
import time
from collections import Counter

from . import inputs, routines, vision, winapi
from . import settings as cfg
from .common import DEBUG, countdown, imwrite, log, rel, stamp


def heal_offsets():
    """Seconds after an F press at which X is pressed: every HEAL_EVERY s through the cooldown,
    starting HEAL_DELAY_POST_F after F ends, until the next F."""
    if cfg.HEAL_EVERY <= 0:
        return []
    offsets, t = [], cfg.F_DURATION + cfg.HEAL_DELAY_POST_F
    while t < cfg.F_DURATION + cfg.F_COOLDOWN:
        offsets.append(t)
        t += cfg.HEAL_EVERY
    return offsets


class Presses:
    """When F and X are due in the current match.

    The first F comes FIRST_PRESS_DELAY after the HUD shows. After every F press at time t:
    X at each of t + heal_offsets(), then the next F at t + F_DURATION + F_COOLDOWN. Nothing is
    pressed while the rune is running.

    A press that couldn't be made (game not in front, HUD hidden) stays due and is made late,
    but only while it's the latest one due: when a later press is due too, the earlier one is
    dropped. So there's never a backlog or a burst of presses."""

    def __init__(self, now):
        self.queue = [(now + cfg.FIRST_PRESS_DELAY, "F")]      # (due time, "F" or "X"), in time order

    def due(self, now):
        """The press to make now, as (due time, "F" or "X"), or None."""
        ready = [p for p in self.queue if p[0] <= now]
        return ready[-1] if ready else None

    def pressed(self, item, now):
        if item[1] == "F":
            self.queue = [(now + off, "X") for off in heal_offsets()]
            self.queue.append((now + cfg.F_DURATION + cfg.F_COOLDOWN, "F"))
        else:
            self.queue = [p for p in self.queue if p[0] > item[0]]

    def next_due(self, now):
        """When the next press that isn't due yet becomes due, or None."""
        later = [t for t, _ in self.queue if t > now]
        return min(later) if later else None

    def next_f(self):
        """When the next F is due (time.monotonic()), or None."""
        return next((t for t, k in self.queue if k == "F"), None)


class Status:
    """What the loop is doing, for the window. Written by the loop's thread and read by the window's, so
    only plain attribute assignments (and the stats Counter, which only grows)."""

    def __init__(self):
        self.state = "starting"
        self.profile = ""
        self.next_f: float | None = None    # time.monotonic() when the next F is due, while in a match
        self.started: float | None = None
        self.stats = Counter()


# The backup: One more round still there after BACKUP_ROUTINE_AFTER clicks runs the storage-full routine. It's
# the only button that can need it: with full gear storage it doesn't start a round, and every other way into
# the forge starts from a different click (the user, 2026-11-23, when a button -> routine table was dropped).
BACKUP_BUTTON, BACKUP_ROUTINE = "click_one_more_round", "storage_full"


def sort_templates(profile):
    """The profile's templates by kind -> (all, clicks, ingame, stops, routine triggers)."""
    templates = profile.templates()
    clicks = [t for t in templates if t.kind == "click"]
    ingame = [t for t in templates if t.kind == "ingame"]
    stops = [t for t in templates if t.kind == "stop"]
    triggers = []
    for t in (t for t in templates if t.kind == "routine" and cfg.RUN_ROUTINES):
        if profile.routine_for(t.name):
            triggers.append(t)
        else:
            log(f"ignoring {t.name}: no matching routine in profile.json "
                f"(it has: {', '.join(profile.routines) or 'none'})")
    return templates, clicks, ingame, stops, triggers


def run(profile, refit=None, keys=None, status=None, start_delay=5):
    """The loop. refit(size) -> the profile to use when the screen turns out to be another size than
    `profile` is fitted to (a fullscreen game switches the display to its own resolution when it comes to
    the front). Default: fit this profile to it. keys: the Hotkeys to obey (the window shares its own, so
    its Pause and Stop buttons do what F8 and F10 do). status: a Status to keep up to date. start_delay:
    the countdown before it starts, for switching to the game from the terminal (the window uses 0: the
    loop waits for the game to be in front anyway)."""
    refit = refit or profile.fit
    status = status or Status()
    templates, clicks, ingame, stops, triggers = sort_templates(profile)
    if not clicks:
        sys.exit(f"No click_*.png templates in {rel(profile.templates_dir)} yet. "
                 "Make them first (snap, then crop).")
    log(f"starting with profile {profile}: {len(clicks)} button(s), {len(ingame)} in-match marker(s), "
        f"{len(stops)} stop sign(s), {len(triggers)} routine trigger(s); "
        f"{sum(t.locked for t in templates)} of {len(templates)} locked to their spot")
    if profile.scale:
        log(f"the profile's images and click spots are resized from {profile.base[0]}x{profile.base[1]} to this "
            f"{profile.screen[0]}x{profile.screen[1]} screen. If something isn't recognised or clicked right, "
            "`check` shows the scores (README.md, Other screen sizes)")
    if not cfg.RUN_ROUTINES:
        log("routines are off (RUN_ROUTINES): full gear storage isn't handled, so One more round just keeps "
            "being clicked")
    else:
        for r, steps in profile.routines.items():
            routines.check_typing(r, steps)        # e.g. SMELT_RATING: stop now, not when storage fills
            for s in steps:
                if "type" in s:
                    log(f"the {r} routine types {routines.describe_type(s['type'])}")
            backup = r == BACKUP_ROUTINE and cfg.BACKUP_ROUTINE_AFTER
            if not any(profile.routine_for(t.name) == r for t in triggers):
                log(f"no routine_{r}*.png template yet, so the {r} routine only runs as a backup"
                    if backup else f"no routine_{r}*.png template yet, so the {r} routine won't run by itself")
            if backup:
                log(f"backup: {BACKUP_BUTTON} still there after {cfg.BACKUP_ROUTINE_AFTER} clicks runs the {r} routine")
        if BACKUP_ROUTINE not in profile.routines:
            log(f"profile {profile.name} has no {BACKUP_ROUTINE} routine, so with full gear storage {BACKUP_BUTTON} "
                f"just keeps being clicked. Record the routine with `routine record`")
    heals = ", ".join(f"{s:g}s" for s in heal_offsets()) or "never"
    log(f"F every {cfg.F_DURATION + cfg.F_COOLDOWN:g}s (first one {cfg.FIRST_PRESS_DELAY:g}s into a match), "
        f"X at {heals} after each F")
    for t in templates:
        if not t.locked:
            log(f"  {t.name} has no .json, so it's searched for on the whole screen (re-crop it to lock it)")
    if not ingame:
        log("no ingame*.png template, so F and X get pressed on every screen")
    if start_delay:
        countdown(start_delay)

    screen, keys = vision.Screen(), keys or winapi.Hotkeys()
    stats = status.stats
    start = status.started = time.monotonic()
    status.profile = str(profile)
    presses = None                     # F/X timing for the current match; None = not in a match
    last_ingame = last_known = last_stuck_shot = start
    stuck_shots = 0
    rearm_at = {}                      # button name -> when it may be clicked again
    streak_name, streak = None, 0      # the button clicked this many times without leaving the screen
    save_next = None                   # file name prefix: save the next frame (what a click led to)
    routine_done_at = None             # when the last routine finished, until something is recognised
    routine_since_match = False        # a routine ran and no match has started since
    focus_warned = last_refocus = start - 3600
    away_since = None                  # when the game stopped being the front window
    sizes_checked = False
    wait_after = {k.lower(): v for k, v in cfg.AFTER_CLICK_WAIT_FOR.items()}

    def act(fn, *args):
        """Send input only while the game is the front window and has been for FOCUS_SETTLE. Never
        pulls focus away from you: if you're on another window, the action is simply skipped and the
        next scan decides again."""
        if away_since is not None or not winapi.game_in_front():
            return False
        fn(*args)
        return True

    while True:
        keys.poll()
        if keys.quit:
            break
        now = time.monotonic()
        if cfg.MAX_HOURS and now - start > cfg.MAX_HOURS * 3600:
            log(f"MAX_HOURS ({cfg.MAX_HOURS}) reached")
            break

        # Game not in front: you're probably using another window, so leave it alone. Only if nobody
        # has touched mouse/keyboard for a while (e.g. something stole focus overnight) bring it back.
        front = winapi.game_in_front()
        refocused = False
        if not front and now - last_refocus >= cfg.REFOCUS_EVERY \
                and winapi.user_idle_seconds() >= cfg.IDLE_BEFORE_REFOCUS:
            last_refocus = now
            front = refocused = winapi.ensure_focus()
            if refocused:
                log(f"no mouse/keyboard input for {cfg.IDLE_BEFORE_REFOCUS}s and the game wasn't in front "
                    "- brought it back")
            elif now - focus_warned > 600:
                log("couldn't bring the game back to the front (minimised? closed?) - will keep trying")
                focus_warned = now
        if not front:
            status.state = "waiting for the game to be the front window"
            if away_since is None:
                away_since = now
                log("the game isn't the front window - skipping presses and clicks until it's back in front")
        elif away_since is not None or refocused:
            # Games often swallow input for a moment after getting focus back (the first click can
            # just count as activating the window), so wait, then look at the screen afresh.
            if away_since is not None:
                log(f"game is back in front after {(now - away_since) / 60:.1f} min - "
                    f"waiting {cfg.FOCUS_SETTLE:g}s before sending anything")
            away_since = None
            keys.sleep(cfg.FOCUS_SETTLE)
            continue

        # The screen's size can change under the bot: a game in exclusive fullscreen switches the display
        # to its own resolution when it's in front (and Windows switches back when you alt-tab out), and
        # the size was first read in the terminal. Follow it while the game is in front; while it isn't,
        # nothing is pressed or clicked anyway, and alt-tabbing back and forth doesn't re-fit each time.
        screen.refresh()
        if front and screen.size != profile.screen:
            w, h = screen.size
            try:
                profile = refit(screen.size)
            except SystemExit as e:
                log(f"the screen is now {w}x{h}, and there's no profile for it - stopping. {e}")
                break
            templates, clicks, ingame, stops, triggers = sort_templates(profile)
            log(f"the screen is now {w}x{h} - using profile {profile}")
            status.profile = str(profile)
            sizes_checked = False

        frame = screen.grab()
        small = vision.shrink(frame)
        if front and not sizes_checked:
            vision.warn_size(templates, frame)
            sizes_checked = True
        if save_next:
            path = DEBUG / f"{save_next}_{stamp()}.png"
            imwrite(path, frame)
            log(f"saved {rel(path)}")
            save_next = None

        if routine_done_at is not None:
            if last_known > routine_done_at:
                routine_done_at = None     # something recognised since: the routine got the game going
            elif now - routine_done_at > cfg.ROUTINE_RECOVER:
                path = DEBUG / f"routine_failed_{stamp()}.png"
                imwrite(path, frame)
                log(f"nothing recognised for {cfg.ROUTINE_RECOVER:g}s after the routine - stopping. "
                    f"Screenshot: {rel(path)}")
                break

        hit = vision.best(small, stops)
        if hit:
            path = DEBUG / f"stop_{stamp()}.png"
            imwrite(path, frame)
            log(f"saw {hit[0].name} ({hit[1]:.2f}) - stopping. Screenshot: {rel(path)}")
            break

        # Routine triggers (the storage-full message), before buttons. Then the backup: One more round still
        # there after BACKUP_ROUTINE_AFTER clicks (it never starts a round with full storage, even when the
        # message wasn't seen) runs the storage-full routine instead of being clicked again.
        name = why = None
        hit = vision.best(small, triggers)
        if hit:
            t, score, _ = hit
            name, why = profile.routine_for(t.name), f"saw {t.name} ({score:.2f})"
        elif (cfg.RUN_ROUTINES and cfg.BACKUP_ROUTINE_AFTER and streak >= cfg.BACKUP_ROUTINE_AFTER
              and (streak_name or "").lower() == BACKUP_BUTTON and BACKUP_ROUTINE in profile.routines):
            again = [t for t in clicks if t.name == streak_name and rearm_at.get(t.name, 0) <= now]
            if vision.best(small, again, skip_dimmed=True):
                name = BACKUP_ROUTINE
                why = f"{streak_name} is still there after {streak} clicks"
        if name:
            path = DEBUG / f"routine_{name}_{stamp()}.png"
            imwrite(path, frame)
            if routine_since_match:
                log(f"{why} again, and no match has started since the last {name} routine "
                    f"- stopping instead of looping. Screenshot: {rel(path)}")
                break
            log(f"{why} - running the {name} routine. Screenshot: {rel(path)}")
            status.state, status.next_f = f"running the {name} routine", None
            if not routines.run(name, profile.routines[name], screen, keys):
                break                      # F10 during the routine
            stats[f"{name} routines"] += 1
            routine_since_match = True
            routine_done_at = last_known = time.monotonic()
            presses, rearm_at, streak_name, streak = None, {}, None, 0
            continue

        # Buttons. One still on screen REPEAT_CLICK_AFTER after its click is clicked again: the
        # click didn't take. A dimmed one (greyed out / behind a translucent layer) is never clicked.
        armed = [t for t in clicks if rearm_at.get(t.name, 0) <= now]
        hit = vision.best(small, armed, skip_dimmed=True)
        if hit:
            last_known = now
            t, score, pos = hit
            target = vision.click_point(t, pos, profile.click_at)
            park = screen.to_screen((frame.shape[1] // 2, frame.shape[0] // 2))
            if act(inputs.click, *screen.to_screen(target), park):
                stats[t.name] += 1
                rearm_at[t.name] = now + cfg.REPEAT_CLICK_AFTER
                streak = streak + 1 if streak_name == t.name else 1
                streak_name = t.name
                status.state, status.next_f = f"clicked {t.name}" + (f" (try {streak})" if streak > 1 else ""), None
                log(f"clicked {t.name} ({score:.2f}) at {target[0]},{target[1]}"
                    + (f" - try {streak}, the last click didn't take" if streak > 1 else ""))
                wait = wait_after.get(t.name.lower(), cfg.AFTER_CLICK_WAIT)
                if streak == cfg.NO_EFFECT_AFTER:
                    # Save what the screen shows right after this click (for "One more round" with full
                    # storage, that's when the storage-full message is up).
                    save_next = f"noeffect_{t.name}"
                    log(f"{t.name} is still there after {streak} clicks - saving a screenshot of the screen "
                        f"{wait:g}s after this click. Still retrying every {cfg.REPEAT_CLICK_AFTER:g}s.")
                presses = None             # whatever comes next is a fresh match
                keys.sleep(wait)
                continue
            keys.sleep(cfg.SCAN_EVERY)     # game not in front: nothing kept, the next scan decides again
            continue
        if vision.best(small, [t for t in clicks if t not in armed]):
            last_known = now               # a button we just clicked is still up: give it time
            keys.sleep(cfg.SCAN_EVERY)
            continue
        streak_name, streak = None, 0      # no button on screen any more: the last click worked

        in_match = bool(vision.best(small, ingame)) if ingame else True
        if in_match:
            last_ingame = last_known = now
            routine_since_match = False
            if presses is None:
                presses = Presses(now)
                if ingame:
                    stats["matches"] += 1
                    log("in a match")
            item = presses.due(now)
            if item and (act(inputs.press_repeated, cfg.ABILITY_KEY, cfg.ABILITY_PRESSES, cfg.ABILITY_SPAN)
                         if item[1] == "F" else act(inputs.press, cfg.HEAL_KEY)):
                presses.pressed(item, now)
                stats[f"{item[1]} presses"] += 1
        elif presses is not None and now - last_ingame > cfg.MATCH_LOST_GRACE:
            presses = None

        if last_known > last_stuck_shot:
            stuck_shots = 0                # something was recognised since the last stuck screenshot
        if now - last_known > cfg.STUCK_AFTER and now - last_stuck_shot > cfg.STUCK_AFTER:
            last_stuck_shot = now
            if stuck_shots < cfg.STUCK_SHOTS_MAX:
                stuck_shots += 1
                path = DEBUG / f"stuck_{stamp()}.png"
                imwrite(path, frame)
                log(f"nothing recognised for {int(now - last_known) // 60} min - saved {rel(path)} "
                    f"({stuck_shots}/{cfg.STUCK_SHOTS_MAX}). If it's a screen the bot should get past, "
                    "crop a click_ template from it.")
                if stuck_shots == cfg.STUCK_SHOTS_MAX:
                    log("no more stuck screenshots until something is recognised again")

        if in_match:
            status.state = "in a match" if ingame else "pressing F and X on every screen (no ingame images)"
        else:
            status.state = "in a match, HUD hidden" if presses else "watching the screen (nothing to click)"
        status.next_f = presses.next_f() if presses else None

        # Wake up right when the next press is due. A press that's already overdue (HUD hidden,
        # game not in front) is retried at the normal scan rate, not in a tight loop.
        nap = cfg.SCAN_EVERY
        wake = presses.next_due(now) if presses else None
        if wake is not None:
            nap = min(nap, max(0.05, wake - time.monotonic()))
        keys.sleep(nap)

    status.state, status.next_f = "stopped", None
    mins = (time.monotonic() - start) / 60
    done = ", ".join(f"{k}: {v}" for k, v in stats.items()) or "nothing done"
    log(f"stopped after {mins:.0f} min. {done}")
