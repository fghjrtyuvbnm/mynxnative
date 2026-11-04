import subprocess, sys, tempfile
from pathlib import Path
src = Path('dm/host/hle_uemalloc.c').read_text()
gate = src[src.index('static void obj_made('):src.index('// Whether [a, a + n)')]
prefix = r"""
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
typedef struct { uint8_t *base; char build_id[33]; } module_t;
static const module_t *g_ue_module;
static void *g_vt[32];
static const char *g_what = "";
#define LOG(...) ((void)g_what)
"""
test = r"""
int main(void) {
    uint8_t *b = calloc(1, 0x4e8d000);
    if (!b) return 2;
    module_t m = {b, "724c36a143f3f2257bf4f8bb37a0477c"};
    g_ue_module = &m;
    void **global = (void **)(b + 0x4e64670);
    void ***alias = (void ***)(b + 0x4e8c2a8);
    *(void ****)(b + 0x49ad2a0) = alias;
    void *object = NULL;
    uint64_t r[] = {(uintptr_t)&object};
    m.build_id[0] = '0';
    obj_made(r, 0);
    if (object != g_vt || *global || *alias) return 3;
    m.build_id[0] = '7';
    r[0] = (uintptr_t)(b + 0x4a170f0);
    obj_made(r, 0);
    if (*(void **)(uintptr_t)r[0] != g_vt || *global != (void *)(uintptr_t)r[0] || *alias != global) {
        puts("Torneko allocator was not published through both globals");
        return 1;
    }
    free(b);
    return 0;
}
"""
with tempfile.TemporaryDirectory() as d:
    path = Path(d)
    (path/'gate.c').write_text(prefix+gate+test)
    subprocess.run(['clang',str(path/'gate.c'),'-o',str(path/'gate.exe')],check=True)
    sys.exit(subprocess.call([str(path/'gate.exe')]))
