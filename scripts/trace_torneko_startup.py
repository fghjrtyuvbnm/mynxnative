"""Install temporary diagnostics into the runner checkout only."""
from pathlib import Path


def replace(path, old, new):
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if text.count(old) != 1:
        raise ValueError(f'Unexpected diagnostic anchor in {path}')
    p.write_text(text.replace(old, new), encoding='utf-8')


main = 'dm/host/main.c'
replace(main, '    probe_install();', '''    for (int k = 0; k < g_nmod; k++) {
        if (!strcmp(g_mod[k].name, "main") && !strcmp(g_mod[k].build_id, "724c36a143f3f2257bf4f8bb37a0477c")) {
            char watch[40];
            snprintf(watch, sizeof watch, "%llx+8", (unsigned long long)(uintptr_t)(g_mod[k].base + 0x4e64670));
            setenv("DM_PROBE_WATCH", watch, 1);
        }
    }
    probe_install();''')
replace(main, '    ((fn0)req("_init_libc2"))();', '''    void dm_torneko_trace(const char *);
    dm_torneko_trace("after nninitStartup");
    ((fn0)req("_init_libc2"))();
    dm_torneko_trace("after _init_libc2");''')
replace(main, '    run_module_inits();', '''    run_module_inits();
    dm_torneko_trace("after module initializers");''')
replace('dm/host/hle_uemalloc.c', 'static void obj_made(', '''void dm_torneko_trace(const char *phase) {
    if (!g_ue_module || strcmp(g_ue_module->build_id, "724c36a143f3f2257bf4f8bb37a0477c")) return;
    uint8_t *b = g_ue_module->base;
    LOG("Torneko trace %s: allocator=%p alias=%p", phase,
        *(void **)(b + 0x4e64670), *(void **)(b + 0x4e8c2a8));
}

static void obj_made(''')
replace('dm/host/hle_uemalloc.c', '        *alias = global;', '''        *alias = global;
        dm_torneko_trace("after registration");''')
