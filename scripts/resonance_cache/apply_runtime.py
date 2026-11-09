"""Install the external-directory launcher without changing the shader translation chain."""
import pathlib
import shutil
import subprocess
import sys
from build_cache_launcher import SOURCE

TABLET_SOURCES = ('DmGamepad.m', 'TouchLayoutPolicy.h', 'TabletPadLayout.h',
                  'DmIOS-Bridging-Header.h', 'Launcher.swift', 'TabletPadLauncher.swift')


def install_tablet_sources(repo):
    source = pathlib.Path(__file__).resolve().parents[2] / 'dm/ios/Sources'
    target = repo / 'dm/ios/Sources'
    for name in TABLET_SOURCES:
        if (source/name).resolve() != (target/name).resolve():
            shutil.copyfile(source/name, target/name)

def replace_once(text,old,new):
    if text.count(old)!=1:raise ValueError('Pinned iOS launcher source changed; review the external-data patch')
    return text.replace(old,new,1)

def apply(repo, source=SOURCE):
    repo=pathlib.Path(repo).resolve()
    if subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()!=source:raise ValueError('Unexpected runtime base source')
    sources=repo/'dm/ios/Sources';runtime=pathlib.Path(__file__).resolve().parent
    sys.path.insert(0,str(runtime.parent))
    from package_policy import install_controller_policy, install_launcher_policy
    install_launcher_policy(repo)
    install_controller_policy(repo)
    for name in ('GameDataCore.swift','ExternalGameData.swift','ShaderCache.swift'):shutil.copyfile(runtime/name,sources/name)
    main=sources/'main.m';text=main.read_text(encoding='utf-8')
    if 'dm_external_data_configured' not in text:
        text=replace_once(text,'#include <unistd.h>','#include <unistd.h>\n#include <stdbool.h>')
        text=replace_once(text,'static char *g_argv[4]; static int g_argc;',
            'static char *g_argv[4]; static int g_argc;\nextern bool dm_external_data_configured(void);\nstatic int uses_external_data(void) { return [[NSBundle.mainBundle objectForInfoDictionaryKey:@"DMExternalGameData"] boolValue]; }')
        text=replace_once(text,'    if (!romfs) {', '    if (!romfs && !uses_external_data()) {')
        text=replace_once(text,'    fprintf(stderr, "boot: game files %s\\n", romfs.fileSystemRepresentation);',
            '    if (romfs && !uses_external_data()) fprintf(stderr, "boot: game files %s\\n", romfs.fileSystemRepresentation);')
        text=replace_once(text,'    setenv("DM_ROMFS", romfs.fileSystemRepresentation, 0);',
            '    if (!uses_external_data()) setenv("DM_ROMFS", romfs.fileSystemRepresentation, 0);')
        text=replace_once(text,'    dm_host_preload_start(g_argc, g_argv);   // Module tables',
            '    if (!uses_external_data()) dm_host_preload_start(g_argc, g_argv);   // Module tables')
        text=replace_once(text,'    static int once; if (once++ || !g_boot_ok) return;',
            '    static int once; if (once || !g_boot_ok) return;\n    if (uses_external_data() && !dm_external_data_configured()) { fprintf(stderr, "boot: external data is not ready\\n"); return; }\n    once = 1;\n    if (uses_external_data()) dm_host_preload_start(g_argc, g_argv); // Only after directory access and settings are committed.')
        main.write_text(text,encoding='utf-8',newline='\n')
    launcher=sources/'Launcher.swift';text=launcher.read_text(encoding='utf-8')
    if '@ObservedObject private var data = ExternalGameDataStore.shared' not in text:
        text=replace_once(text,'    let play: () -> Void\n    @State private var memory',
            '    let play: () -> Void\n    @ObservedObject private var data = ExternalGameDataStore.shared\n    @State private var dataPicker = false\n    @State private var confirmDataClear = false\n    @State private var memory')
        text=replace_once(text,'                List {\n                    ForEach(m.sections',
            '''                List {
                    if data.enabled {
                        Section {
                            Text(data.folderName)
                            Text(data.message).font(.footnote).foregroundStyle(.secondary)
                            if data.busy { ProgressView() }
                            Button("Choose data folder") { dataPicker = true }.disabled(data.busy || data.started)
                            Button("Check folder again") { data.recheck() }.disabled(data.busy || data.started)
                            Button("Import all data") { data.importAll() }
                                .disabled(!data.ready || data.imported || data.busy || data.started)
                            Button("Clear game data", role: .destructive) { confirmDataClear = true }
                                .disabled(data.busy || data.started)
                        } header: {
                            Text("Game data")
                        } footer: {
                            Text("Play from the selected folder or import all data for offline play.")
                        }
                    }
                    ForEach(m.sections''')
        text=replace_once(text,'        .preferredColorScheme(.dark)\n        .task {',
            '''        .preferredColorScheme(.dark)
        .sheet(isPresented: $dataPicker) {
            GameDataFolderPicker(picked: { url in dataPicker = false; data.choose(url) }, cancelled: { dataPicker = false })
        }
        .alert("Clear game data?", isPresented: $confirmDataClear) {
            Button("Clear game data", role: .destructive) { data.clearData() }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This removes local game data, caches and logs. Your saves and launcher settings are kept. The external folder is untouched.")
        }
        .onAppear { data.restoreIfNeeded() }
        .task {''')
        text=replace_once(text,'}.controlSize(.large)\n        if #available(iOS 26.0, *)',
            '}.controlSize(.large).disabled(data.enabled && (!data.ready || data.busy || data.started))\n        if #available(iOS 26.0, *)')
        text=replace_once(text,'if ProcessInfo.processInfo.environment["DM_LAUNCHER"] == "0" {',
            'if ProcessInfo.processInfo.environment["DM_LAUNCHER"] == "0" && !ExternalGameDataStore.shared.enabled {')
        old='''    guard let url = Bundle.main.resourceURL?.appendingPathComponent("dm/launcher.json"), let data = try? Data(contentsOf: url) else { return false }
    guard let file = try? JSONDecoder().decode(SettingsFile.self, from: data), !file.settings.isEmpty else { fputs("[RED] launcher: dm/launcher.json cannot be read; starting the game\\n", stderr); return false }'''
        new='''    var settings: [Setting] = []
    if let url = Bundle.main.resourceURL?.appendingPathComponent("dm/launcher.json"), let bytes = try? Data(contentsOf: url) {
        if let file = try? JSONDecoder().decode(SettingsFile.self, from: bytes) { settings = file.settings }
    }
    if settings.isEmpty && !ExternalGameDataStore.shared.enabled { return false }'''
        text=replace_once(text,old,new)
        factory = 'makeLauncherModel' if 'private func makeLauncherModel(' in text else 'LauncherModel'
        text=replace_once(text,f'    let model = {factory}(file.settings)',f'    let model = {factory}(settings)')
        if f'{factory}(file.settings).applySaved()' in text:
            text=replace_once(text,f'{factory}(file.settings).applySaved()', f'{factory}(settings).applySaved()')
        text=replace_once(text,'''        host = nil
        model.apply()
        h.dismiss(animated: false) { done() }''',
            '''        model.apply()
        ExternalGameDataStore.shared.activate { ready in
            guard ready else { return }
            host = nil
            h.dismiss(animated: false) { done() }
        }''')
        text=replace_once(text,'fputs("launcher: \\(file.settings.count) settings shown\\n", stderr)',
            'fputs("launcher: \\(model.settings.count) settings shown\\n", stderr)')
        launcher.write_text(text,encoding='utf-8',newline='\n')
    print('External folder selection, persistent access and deferred game preload installed')

if __name__=='__main__':apply(sys.argv[1])
