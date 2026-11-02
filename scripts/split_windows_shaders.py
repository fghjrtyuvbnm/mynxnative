"""Run the pinned shader scanner with portable source labels on Windows."""
import os
_native_relpath = os.path.relpath

def relative_label(path, root):
    return _native_relpath(path, root).replace('\\', '/')

if __name__ == '__main__':
    from pathlib import Path
    import sys
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'dm/gfx/tools'))
    import shader_split
    if os.name == 'nt':
        shader_split.os.path.relpath = relative_label
    shader_split.main()
