"""Compile legacy and modern GLSL through the real offline GL translator."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'dm/gfx/tools'))
import gl_shaders


class GLVersionTests(unittest.TestCase):
    def compile_source(self, source, stage):
        source = source.encode()
        key = hashlib.sha256(source).hexdigest()[:16]
        with tempfile.TemporaryDirectory() as temp:
            result = gl_shaders.translate(source, stage, key, temp)
            self.assertIsInstance(result, tuple, str(result))
            metal, fields = result
            self.assertIn('gl_'+key+'_'+stage[0], Path(metal).read_text())
            self.assertTrue(fields)

    def test_es300_fragment_preserves_version_branch(self):
        self.compile_source('''#version 300 es
precision mediump float;
#if __VERSION__ != 300
#error Original ES 300 preprocessing was not preserved
#endif
in vec2 uv;
uniform sampler2D image;
out vec4 color;
void main() { color = texture(image, uv); }
''', 'frag')

    def test_es300_vertex_preserves_varying(self):
        self.compile_source('''#version 300 es
in vec4 position;
out mediump vec2 uv;
void main() { gl_Position = position; uv = position.xy; }
''', 'vert')

    def test_existing_es100(self):
        self.compile_source('''#version 100
precision mediump float;
varying vec2 uv;
uniform sampler2D image;
void main() { gl_FragColor = texture2D(image, uv); }
''', 'frag')

    def test_existing_es320(self):
        self.compile_source('''#version 320 es
precision mediump float;
layout(location=0) in vec2 uv;
layout(location=0) out vec4 color;
void main() { color = vec4(uv, 0.0, 1.0); }
''', 'frag')


if __name__ == '__main__':
    unittest.main()
