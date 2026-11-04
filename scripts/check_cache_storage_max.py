"""Exercise the production cache-capacity query with valid and invalid metadata."""
from pathlib import Path
import subprocess
import tempfile

source = Path('dm/host/hle_fs.c').read_text()
start = source.index('HLE_FORCE("_ZN2nn2fs18GetCacheStorageMaxEPiPl"')
body = source[start:source.index('\n}', start) + 2]
prefix = r"""
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
typedef int Result;
#define RES_FAIL 1
#define RES_OK 0
#define LOG(...) ((void)0)
#define HLE_FORCE(symbol, description, result, name, ...) result name(__VA_ARGS__)
"""
test = r"""
int main(int argc, char **argv) {
    assert(argc == 2);
    int index = -2;
    int64_t size = -2;
    assert(h_fs_CacheMax(&index, &size) == RES_FAIL);
    FILE *f = fopen(argv[1], "wb");
    assert(f);
    uint8_t data[0x4000] = {0};
    assert(fwrite(data, 1, sizeof data, f) == sizeof data);
    fclose(f);
#ifdef _WIN32
    _putenv_s("DM_CONTROL_NACP", argv[1]);
#else
    setenv("DM_CONTROL_NACP", argv[1], 1);
#endif
    assert(h_fs_CacheMax(&index, &size) == RES_OK && index == 0 && size == 0);
    data[0x3180] = 0x12;
    data[0x3183] = 0x40;
    data[0x3188] = 0x34;
    data[0x3189] = 0x12;
    f = fopen(argv[1], "wb");
    fwrite(data, 1, sizeof data, f);
    fclose(f);
    assert(h_fs_CacheMax(&index, &size) == RES_OK && index == 0x1234 && size == 0x40000012);
    f = fopen(argv[1], "wb");
    fwrite(data, 1, 0x3188, f);
    fclose(f);
    assert(h_fs_CacheMax(&index, &size) == RES_FAIL && index == 0x1234 && size == 0x40000012);
    assert(h_fs_CacheMax(NULL, &size) == RES_FAIL);
    data[0x3187] = 0x80;
    f = fopen(argv[1], "wb");
    fwrite(data, 1, sizeof data, f);
    fclose(f);
    assert(h_fs_CacheMax(&index, &size) == RES_FAIL);
    puts("PASS cache capacity metadata: zero, nonzero, absent, truncated and out of range");
    return 0;
}
"""
with tempfile.TemporaryDirectory() as d:
    folder = Path(d)
    c = folder/'capacity.c'
    c.write_text(prefix + body + test)
    binary = folder/'capacity.exe'
    subprocess.run(['clang', str(c), '-o', str(binary)], check=True)
    subprocess.run([str(binary), str(folder/'control.nacp')], check=True)
