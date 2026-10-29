#!/usr/bin/env python3
"""Stage the 2in1 SceneBoard runtime using shared strict asset verification."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from sceneboard_assets import main, patch_cem_user_id

if __name__ == "__main__":
    main("2in1")
