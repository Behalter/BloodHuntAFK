# PyInstaller build of the release (run build.ps1, not this directly).
#
# One folder with two exes that share the same code (_internal\):
#   BloodHuntAFK.exe          the window (no console)
#   BloodHuntAFK-console.exe  the commands (snap, crop, check, ...): the window's Setup tools open it
# Both ask for administrator rights when they start (the game ignores input from programs with lower
# rights), unless BLOODHUNT_NO_ADMIN=1 (build.ps1 -NoAdmin, for test builds).
# bloodhunt\settings.py goes in as defaults\settings.py: the copy put back if the settings.py next to the
# exe is deleted. build.ps1 copies settings.py, the README and the profiles next to the exes.
import os

admin = os.environ.get("BLOODHUNT_NO_ADMIN") != "1"

a = Analysis(
    ["BloodHuntAFK.py"],
    datas=[("bloodhunt/settings.py", "defaults")],
    excludes=["matplotlib", "PIL", "pytest", "IPython"],
)
# OpenCV's video plugin (ffmpeg, ~40 MB) is only loaded for video files and cameras, which the bot never opens.
a.binaries = [b for b in a.binaries if "opencv_videoio_ffmpeg" not in b[0]]
a.datas = [d for d in a.datas if "opencv_videoio_ffmpeg" not in d[0]]
pyz = PYZ(a.pure)
shared = dict(exclude_binaries=True, debug=False, strip=False, upx=False, uac_admin=admin)
window = EXE(pyz, a.scripts, [], name="BloodHuntAFK", console=False, **shared)
console = EXE(pyz, a.scripts, [], name="BloodHuntAFK-console", console=True, **shared)
coll = COLLECT(window, console, a.binaries, a.datas, strip=False, upx=False, name="BloodHuntAFK")
