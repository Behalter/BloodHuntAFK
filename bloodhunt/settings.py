"""Settings. Change them in the bot's window (Settings and Advanced tabs), or edit this file and re-run.

This file is the only place the values live: the window reads it, and its Save changes just the value on
each line, keeping the comments. Each setting's comment is its help text in the window, so it should make
sense on its own; a comment starting with "..." continues the one above it. In the release, this is the
settings.py next to BloodHuntAFK.exe. Values must be plain: numbers, "text", True/False/None, {...}.

Things that depend on the screen resolution (screen size, fixed click spots) are per profile, in
profiles\\<name>\\profile.json, not here.
"""

# ── Keys ────────────────────────────────────────────────────────────────────
ABILITY_KEY = "f"           # the key to activate Thor's Awakening Rune
HEAL_KEY    = "x"           # the key to heal, pressed during Awakening cooldown
PAUSE_KEY   = 0x77          # pauses and resumes the bot, from any window (0x77 = F8)
QUIT_KEY    = 0x79          # stops the bot, from any window (0x79 = F10)
UNDO_KEY    = 0x78          # `routine record` forgets the last click (0x78 = F9)
ABILITY_PRESSES = 3         # each F is sent this many times (a single F sometimes didn't fire)...
ABILITY_SPAN    = 0.55      # ...the presses starting evenly spread over this many seconds. Once the ability
                            # starts, its animation keeps the later presses from cancelling it (tested by the user).

# ── F and X in a match ──────────────────────────────────────────────────────
F_DURATION         = 60     # seconds Awakening Rune lasts
F_COOLDOWN         = 9      # seconds after Awakening ends before F works again; F is pressed every F_DURATION + F_COOLDOWN seconds.
HEAL_DELAY_POST_F  = 3.5    # first heal this many seconds into the F cooldown; useful because enemies take time to reach you
HEAL_EVERY         = 1      # after the first heal, heal every this many seconds until the F cooldown ends
FIRST_PRESS_DELAY  = 1.5    # first F this many seconds after the HUD first shows in a match
MATCH_LOST_GRACE   = 30     # HUD can vanish briefly (cutscene, death); only after this long is the match "over"

# ── Buttons ─────────────────────────────────────────────────────────────────
AFTER_CLICK_WAIT   = 3      # seconds to wait before checking what's on screen after clicking a button
AFTER_CLICK_WAIT_FOR = {    # ...except these buttons. The storage-full message after "One more round" only
    "click_one_more_round": 1.5,   # shows briefly, so the screen is looked at again sooner.
}
REPEAT_CLICK_AFTER = 5      # a button still on screen this long after it was clicked is clicked again
NO_EFFECT_AFTER    = 3      # after this many clicks on the same button without it ever leaving the screen,
                            # save one screenshot to debug\ (and keep retrying)
CLICK_MIN_CONTRAST = 0.80   # a button with less contrast than this vs its template counts as greyed out
                            # / behind a translucent layer, and isn't clicked

# ── Seeing ──────────────────────────────────────────────────────────────────
MATCH_THRESHOLD = 0.80      # how closely a template must match, 0-1. `check` shows the real scores.
MATCH_THRESHOLD_SCALED = 0.70   # ...the same for images resized to a screen size they weren't cropped at
                            # (the 16x9 profile on a 1280x720 screen). The game draws text at whole font
                            # sizes, so a shrunk copy never quite matches: ONE MORE ROUND scored 0.79 at 720p.
SCAN_EVERY      = 1.5       # seconds between screen checks
MATCH_SCALE     = 0.5       # frames and templates are shrunk by this before matching (speed)
SEARCH_MARGIN   = 80        # images are only looked for this many pixels around where they were
                            # cropped. None = search the whole screen for everything.

# ── The game window ─────────────────────────────────────────────────────────
# The game can be on any monitor: the bot finds its window by these and follows it (only its inside,
# without a title bar, is looked at). With neither set, it looks at the main monitor.
GAME_TITLE = "Marvel Rivals"   # part of the game window's title ("" = don't check)
GAME_CLASS = "UnrealWindow"    # the game window's class ("" = don't check). `check` prints both.
FOCUS_SETTLE        = 1.5   # when the game is back in front, wait this long before sending anything:
                            # games often swallow input right after getting focus back
IDLE_BEFORE_REFOCUS = 120   # if the game isn't the front window (you're on your other monitor), presses and
                            # clicks are skipped until you click back into it. Only after this many seconds
                            # without you touching mouse/keyboard does the bot bring the game back itself.
REFOCUS_EVERY       = 30    # ...and then it tries at most this often

# ── Routines (the storage-full smelt; steps are in profiles\<name>\profile.json) ──
RUN_ROUTINES    = True      # run the storage-full routine when gear storage is full.
                            # False = never smelt: with full storage, One more round keeps being clicked.
SMELT_RATING    = 5600      # the storage-full routine smelts every unlocked item rated this or lower, Legendary
                            # included: it types this into the forge's SHOW RATING filter.
TYPE_GAP        = 0         # extra seconds between characters in a routine's "type" step (each key
                            # press already takes ~0.18 s)
ROUTINE_RECOVER = 60        # after a routine, something must be recognised within this many seconds,
                            # or the bot stops and saves a screenshot
BACKUP_ROUTINE_AFTER = 3    # One more round still there after this many clicks runs the storage-full routine
                            # (0 = never): it doesn't start a round when gear storage is full, so this catches
                            # full storage even if the gear-limit message was missed or its image doesn't match.

# ── Watchdogs ───────────────────────────────────────────────────────────────
STUCK_AFTER     = 600       # seconds with nothing recognised -> save a screenshot to debug\
STUCK_SHOTS_MAX = 6         # ...at most this many in a row (6 x 10 min = 1 hour), then stop saving them
MAX_HOURS       = 12        # stop after this many hours (0 = run until stopped)

# ── Wave-aware mode ─────────────────────────────────────────────────────────
WAVE_AWARE = False          # use visual wave and Rune recognition instead of the original fixed timers
WAVE_AUTHORIZED_TEST = False # enable only in an explicitly authorized test environment
WAVE_REFERENCE = ""         # path to calibrated wave reference recording
WAVE_SCREEN_REFERENCE = ""  # path to calibrated results and hero reference recording
WAVE_HEAL = False           # optional healing during observed combat cooldown; experimental

WAVE_CHRONO = False         # optionally collect available Chrono Rush rewards in wave-aware mode
