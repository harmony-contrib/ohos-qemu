"""Read one regular ext-image file, allowing root/system aliases of one inode."""
from pathlib import Path
import re
import subprocess


def dump_unique_file(image, candidates, directory, executable):
    entries = []
    for index, source in enumerate(candidates):
        stat = subprocess.run([executable, "-R", "stat " + source, str(image)],
                              check=True, capture_output=True, text=True)
        identity = re.search(r"(?m)^Inode: (\d+)\s+Type: regular\s", stat.stdout)
        if not identity:
            # debugfs returns zero even when the path is absent.
            continue
        target = Path(directory) / (str(index) + ".extracted")
        subprocess.run([executable, "-R", f"dump {source} {target}", str(image)],
                       check=True, capture_output=True)
        if not target.is_file() or not target.stat().st_size:
            raise ValueError("image regular file could not be extracted: " + source)
        entries.append((target, source, int(identity[1])))
    if not entries or len({entry[2] for entry in entries}) != 1:
        raise ValueError("image must have one unambiguous regular file inode: " + ", ".join(candidates))
    return entries[0][0], {"image_path": entries[0][1], "image_inode": entries[0][2],
                           "image_path_aliases": [entry[1] for entry in entries]}
