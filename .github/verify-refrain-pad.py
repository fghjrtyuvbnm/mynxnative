"""Check the rendering and touch paths for the compact 2D layout."""
import sys
from pathlib import Path

source = Path(sys.argv[1]).read_text(encoding="utf-8")
assert "if ([self compact2D] && [self dpadAt:p])" in source, "2D touches do not reach the D-pad"
assert "if (![self compact2D] && !_stick[0])" in source, "Hidden stick can still capture touches"
assert "_ring.hidden = _knob.hidden = _tap || [self compact2D]" in source
assert "if (menu) y = [self facePos:B_B].y;" in source, "Menu keys must align with B"
assert source.count("[self compactButtonCenter:b]") == 2, "Auxiliary drawing and hit tests must share coordinates"
assert source.count("[self directionCenter:b]") == 2, "Direction drawing and hit tests must share coordinates"
assert "if (_full) { CGFloat d = dist(p, self.dpadCenter)" in source
assert "if (_tap) { game |= [self gameBegin:t]; continue; }" in source
print("2D overlay integration checks passed")
