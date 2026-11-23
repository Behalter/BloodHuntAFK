#!/usr/bin/env python3
r"""
BloodHuntAFK.py - screen-watching AFK loop for Marvel Rivals Blood Hunt (Windows)

Every SCAN_EVERY seconds it looks at the screen and reacts to what it recognises, so round
length, load times and lag can't knock it out of sync the way a recorded macro would:

  click_*.png    clicked whenever it shows up    (e.g. "One more round", the SPACE skip tag)
  ingame*.png    while visible we're in a match: F every F_DURATION + F_COOLDOWN seconds,
                 and X every HEAL_EVERY seconds during each cooldown (from HEAL_DELAY_POST_F in)
  stop_*.png     stops the bot
  routine_storage_full*.png      runs the storage_full routine from profile.json (smelt, then play on)

Everything that depends on the screen is kept per profile, one per screen shape (16x9, 16x10, ...):
  profiles\<name>\profile.json   the size it was cropped at, buttons clicked at a fixed spot, routine steps
  profiles\<name>\templates\     the cropped images (NAME.png, plus NAME.json: where it was cropped,
                                 so it's only looked for around there)
  profiles\<name>\shots\         screenshots from snap
  profiles\<name>\routines\      the screenshots each routine step was measured on
The profile for your main screen's shape is picked automatically (one cropped at exactly your size
first, if there is one). --profile NAME picks one. On another size of the same shape, its images are
resized and its click spots scaled when the bot starts, so profiles\16x9 works on any 16:9 screen.
Another shape starts with snap, then crop, then routine record (README.md, "Other screen sizes").
Timings, keys and other settings: in the window, or bloodhunt\settings.py (in the release, the
settings.py next to BloodHuntAFK.exe). The window changes just the values in that file.

Setup (once):
  1. Install Python 3 from python.org (tick "Add python.exe to PATH").
  2. python -m venv .venv   then   .venv\Scripts\python.exe -m pip install -r requirements.txt
  3. Put the game in Borderless / Windowed Fullscreen, on any monitor.
  4. Play solo: untick AUTO-FILL TEAMMATES.
  5. Run the terminal as administrator.

With no command it opens the window: Start / Pause / Stop, what the bot is doing, every setting, and
the setup tools (which open the commands below in their own console window).
  python BloodHuntAFK.py                    the window
  python BloodHuntAFK.py help               this text

Commands (run them in the folder this file is in; any of them takes --profile NAME):
  python BloodHuntAFK.py keytest            presses F (like run does) after 5 s: checks the game accepts it
  python BloodHuntAFK.py snap               F8 = save a screenshot   F10 = quit
                                            (makes the profile for this screen size, lists what to capture)
  python BloodHuntAFK.py crop               guided: say what's on each screenshot, box it
  python BloodHuntAFK.py crop NAME [SHOT]   pick a screenshot (or give one), drag a box, Enter saves it
  python BloodHuntAFK.py check [SHOT]       scores every template against the screen (or a screenshot)
  python BloodHuntAFK.py run                the loop.   F8 = pause/resume   F10 = quit
  python BloodHuntAFK.py routine check      draws every routine step's click spot on its screenshot (debug\)
  python BloodHuntAFK.py routine run        does the routine once now, from the Victory/Defeat screen
  python BloodHuntAFK.py routine record     you do the routine by hand; your clicks become its click spots
                                            (F9 = undo the last click, F10 = cancel)
"""

from bloodhunt.commands import main

if __name__ == "__main__":
    main(__doc__)
