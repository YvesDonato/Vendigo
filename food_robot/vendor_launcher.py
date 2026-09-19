"""Entry point installed at /home/admin/food_robot/vendor.py."""

from pathlib import Path
import runpy


PLAYER = Path("/home/admin/auto-dash/food_robot/vendor.py")


if __name__ == "__main__":
    if not PLAYER.is_file():
        raise SystemExit(f"Vendor audio player not found: {PLAYER}")
    print("Food vendor: prerecorded Laura voice + jingle", flush=True)
    runpy.run_path(str(PLAYER), run_name="__main__")
