"""Adapt the official R5 framework to the existing ANGLE renderer."""
from pathlib import Path
import json
import re
import shutil

root = Path.cwd()
sdk = root/'cpp/plugins/cubism'
framework = sdk/'Framework'
plugin = root/'cpp/plugins/krkrlive2d.cpp'

for path in framework.rglob('*'):
    if path.suffix not in ('.cpp','.hpp','.h'):
        continue
    source = path.read_text(encoding='utf-8-sig')
    source = source.replace('CSM_TARGET_IPHONE_ES2','CSM_TARGET_ANGLE_ES2')
    source = source.replace('<OpenGLES/ES2/gl.h>','<GLES2/gl2.h>')
    source = source.replace('<OpenGLES/ES2/glext.h>','<GLES2/gl2ext.h>')
    path.write_text(source,encoding='utf-8')

shaders = sorted((framework/'Rendering/OpenGL/Shaders/StandardES').glob('*'))
shaders = [p for p in shaders if p.suffix in ('.frag','.vert')]
assert shaders, 'Missing R5 shader assets'
header = sdk/'EmbeddedCubismShaders.hpp'
lines = [
    '#pragma once',
    '#include <cstring>',
    '',
    'static csmByte* LoadCubismShader(const std::string path, csmSizeInt* size) {',
]
for path in shaders:
    text = path.read_text(encoding='utf-8-sig')
    assert ')KRKRSHADER"' not in text
    lines.extend([
        f'    if (path == {json.dumps("FrameworkShaders/"+path.name)}) {{',
        f'        static const char source[] = R"KRKRSHADER({text})KRKRSHADER";',
        '        *size = sizeof(source) - 1;',
        '        auto* bytes = new csmByte[sizeof(source)];',
        '        std::memcpy(bytes, source, sizeof(source));',
        '        return bytes;',
        '    }',
    ])
lines.extend([
    '    *size = 0;',
    '    return nullptr;',
    '}',
    '',
    'static void ReleaseCubismShader(csmByte* bytes) { delete[] bytes; }',
])
header.write_text('\n'.join(lines)+'\n',encoding='utf-8')

swift = plugin.read_text(encoding='utf-8')
needle = 'using namespace Live2D::Cubism::Framework;'
assert swift.count(needle)==1
swift = swift.replace(needle,needle+'\n#include "cubism/EmbeddedCubismShaders.hpp"')
needle = '    CubismFramework::Option opt;'
assert swift.count(needle)==1
swift = swift.replace(needle,needle+'\n    opt.LoadFileFunction = LoadCubismShader;\n    opt.ReleaseBytesFunction = ReleaseCubismShader;')
needle = '        CreateRenderer();'
assert swift.count(needle) == 1
swift = swift.replace(needle, """        const auto canvasWidth = GetModel()->GetCanvasWidthPixel();
        const auto canvasHeight = GetModel()->GetCanvasHeightPixel();
        CreateRenderer(canvasWidth > 0 ? static_cast<csmUint32>(canvasWidth) : 1920,
                       canvasHeight > 0 ? static_cast<csmUint32>(canvasHeight) : 1080);""")
plugin.write_text(swift,encoding='utf-8')
core = sdk/'Core/lib/ios/Release-iphoneos/libLive2DCubismCore.a'
assert core.read_bytes().startswith(b'!<arch>\n')
merge = root/'out/ios/release/cubism-core'
merge.mkdir(parents=True,exist_ok=True)
shutil.copyfile(core,merge/core.name)
print('Prepared R5 ANGLE backend,',len(shaders),'embedded shaders and iOS Core archive')

