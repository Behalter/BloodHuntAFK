#!/usr/bin/env python3
r"""
BloodHuntAFK.py - screen-watching AFK loop for Marvel Rivals Blood Hunt (Windows)

Every ~1.5 s it looks at the screen and reacts to what it recognises, so round
length, load times and lag can't knock it out of sync the way a recorded macro would:

  click_*.png    clicked whenever it shows up    (e.g. "One more round", the SPACE skip tag)
  ingame*.png    while visible we're in a match: F every F_DURATION + F_COOLDOWN seconds,
                 and X twice during each cooldown
  stop_*.png     stops the bot
  routine_storage_full*.png      runs the storage_full routine from profile.json (smelt, then play on)

Everything that depends on the screen resolution is kept per profile:
  profiles\<name>\profile.json   screen size, buttons clicked at a fixed spot, routine steps
  profiles\<name>\templates\     the cropped images (NAME.png, plus NAME.json: where it was cropped,
                                 so it's only looked for around there)
  profiles\<name>\shots\         screenshots from snap
  profiles\<name>\routines\      the screenshots each routine step was measured on
The profile made for your main screen's size is picked automatically. --profile NAME picks one.
Timings, keys and other settings: bloodhunt\settings.py

Setup (once):
  1. Install Python 3 from python.org (tick "Add python.exe to PATH").
  2. pip install mss opencv-python numpy pydirectinput
  3. Put the game in Borderless / Windowed Fullscreen on your main monitor.

Commands (run them in the folder this file is in; any of them takes --profile NAME):
  python BloodHuntAFK.py keytest            presses F (like run does) after 5 s: checks the game accepts it
  python BloodHuntAFK.py snap               F8 = save a screenshot   F10 = quit
                                            (snap --profile NEWNAME starts a profile for this screen size)
  python BloodHuntAFK.py crop NAME [SHOT]   pick a screenshot (or give one), drag a box, Enter saves it
  python BloodHuntAFK.py check [SHOT]       scores every template against the screen (or a screenshot)
  python BloodHuntAFK.py run                the loop.   F8 = pause/resume   F10 = quit
  python BloodHuntAFK.py routine check      draws every routine step's click spot on its screenshot (debug\)
  python BloodHuntAFK.py routine run        does the routine once now, from the Victory/Defeat screen
"""

from bloodhunt.commands import main

if __name__ == "__main__":
    main(__doc__)
