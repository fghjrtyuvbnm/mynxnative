"""Restore a previous build capture against the pinned registered profile."""
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile

from remap import remap

repo, legacy, metadata, fallback_map, dest, archive = map(Path, sys.argv[1:])
meta = json.loads(metadata.read_bytes())
state = meta["state"]
dest.mkdir()
title, version = state["title"], state["version"]
profile = repo / "dm/games" / title
recorded_map = None
with tarfile.open(legacy) as package:
    for member in package:
        if not member.isfile():
            continue
        path = member.name.removeprefix("./")
        if path.endswith("/shader_map.tsv"):
            recorded_map = package.extractfile(member).read().decode("utf-8")
        if path.startswith(("shader/pkg/", f"patched_{version}/", f"extract/{version}/")) or path == "shader/pso_pairs.tsv":
            target = dest / path
            assert target.resolve().is_relative_to(dest.resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.extractfile(member) as src, target.open("xb") as out:
                shutil.copyfileobj(src, out)
assert recorded_map is not None or state["key"] == "arceus"
old_map = recorded_map or fallback_map.read_text(encoding="utf-8")
new_map = (profile / "shader_map.tsv").read_text(encoding="utf-8")
os.environ.update(GAME=title, DM_GAME=title)
sys.path[:0] = [str(repo / n) for n in ("dm/gfx/tools", "dm/tools", "dm/games")]
remap(dest / "shader", old_map, new_map)
assert state["main_build"] in (dest / f"patched_{version}/main.fixups.tsv").read_text()
marker, = [l.split("\t")[1] for l in (profile / "game.tsv").read_text().splitlines() if l.startswith("romfs_marker\t")]
marker_path = dest / f"extract/{version}/RomFS" / marker
assert marker_path.resolve().is_relative_to(dest.resolve())
marker_path.parent.mkdir(parents=True, exist_ok=True)
# --prepare-xcode checks marker presence. DM_COPY_GAME_RESOURCES=NO keeps
# this compile-only placeholder outside the finished package.
marker_path.touch(exist_ok=True)
state["marker"] = marker
(dest / "game-assets.json").write_text(json.dumps(meta["assets"]))
(dest / "build-state.json").write_text(json.dumps(state))
with tarfile.open(archive, "w:xz", preset=1) as package:
    for child in sorted(dest.iterdir()):
        package.add(child, child.name)
