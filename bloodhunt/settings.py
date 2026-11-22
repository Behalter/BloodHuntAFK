"""Settings. Edit these and re-run.

Things that depend on the screen resolution (screen size, fixed click spots) are per profile, in
profiles\\<name>\\profile.json, not here.
"""

# ── Keys ────────────────────────────────────────────────────────────────────
ABILITY_KEY = "f"           # Awakening Rune
HEAL_KEY    = "x"           # heal
PAUSE_KEY   = 0x77          # F8   (virtual-key codes: learn.microsoft.com/windows/win32/inputdev/virtual-key-codes)
QUIT_KEY    = 0x79          # F10
ABILITY_PRESSES = 3         # each F is sent this many times, the presses starting evenly spread over
ABILITY_SPAN    = 0.55      # this many seconds: a single F sometimes didn't fire. Once the ability starts,
                            # its animation keeps the later presses from cancelling it (tested by the user).

# ── F and X in a match ──────────────────────────────────────────────────────
F_DURATION         = 60     # seconds Awakening Rune lasts
F_COOLDOWN         = 10     # seconds after it ends before F works again. F is pressed every F_DURATION + F_COOLDOWN.
HEAL_EVERY         = 2      # X every this many seconds through the cooldown, timed from the last F press:
                            # 2 -> 62, 64, 66, 68 s after F (first one HEAL_EVERY after F ends). 0 = no X.
FIRST_PRESS_DELAY  = 1.5    # seconds after the HUD first shows in a match (prep phase is ~15 s; F works in it)
MATCH_LOST_GRACE   = 30     # HUD can vanish briefly (cutscene, death); only after this long is the match "over"

# ── Buttons ─────────────────────────────────────────────────────────────────
AFTER_CLICK_WAIT   = 4      # seconds to wait after clicking a button
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
SCAN_EVERY      = 1.5       # seconds between screen checks
MATCH_SCALE     = 0.5       # frames and templates are shrunk by this before matching (speed)
SEARCH_MARGIN   = 80        # images are only looked for this many pixels around where they were
                            # cropped. None = search the whole screen for everything.

# ── The game window ─────────────────────────────────────────────────────────
# The game must be on the PRIMARY monitor (Settings > Display > "Make this my main display").
GAME_TITLE = "Marvel Rivals"   # part of the game window's title ("" = don't check)
GAME_CLASS = "UnrealWindow"    # the game window's class ("" = don't check). `check` prints both.
FOCUS_SETTLE        = 1.5   # when the game is back in front, wait this long before sending anything:
                            # games often swallow input right after getting focus back
IDLE_BEFORE_REFOCUS = 120   # if the game isn't the front window (you're on your other monitor), presses and
                            # clicks are skipped until you click back into it. Only after this many seconds
                            # without you touching mouse/keyboard does the bot bring the game back itself.
REFOCUS_EVERY       = 30    # ...and then it tries at most this often

# ── Routines (the storage-full smelt; steps are in profiles\<name>\profile.json) ──
TYPE_GAP        = 0         # extra seconds between characters in a routine's "type" step (each key
                            # press already takes ~0.18 s)
ROUTINE_RECOVER = 60        # after a routine, something must be recognised within this many seconds,
                            # or the bot stops and saves a screenshot

# ── Watchdogs ───────────────────────────────────────────────────────────────
STUCK_AFTER     = 600       # seconds with nothing recognised -> save a screenshot to debug\
STUCK_SHOTS_MAX = 6         # ...at most this many in a row (6 x 10 min = 1 hour), then stop saving them
MAX_HOURS       = 10        # stop after this many hours (0 = run until stopped)
