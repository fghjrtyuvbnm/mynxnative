// The selected directory stays security-scoped for the complete native game session.
import Foundation
import SwiftUI
import UIKit
import UniformTypeIdentifiers

private final class DefaultsGameDataBookmarks: GameDataBookmarks {
    private let key = "nxnative.external-data." + (Bundle.main.bundleIdentifier ?? "game")
    func read() -> Data? { UserDefaults.standard.data(forKey: key) }
    func write(_ data: Data) throws {
        UserDefaults.standard.set(data, forKey: key)
        guard UserDefaults.standard.data(forKey: key) == data else { throw GameDataError.unavailable }
    }
    func clear() { UserDefaults.standard.removeObject(forKey: key) }
}
private final class ScopedGameDataAccess: GameDataAccess {
    let expected: GameDataIdentity
    let marker: String
    let shaderCache: ShaderCache?
    private var scopes: [URL: Int] = [:]
    init(expected: GameDataIdentity, marker: String, shaderCache: ShaderCache?) {
        self.expected = expected; self.marker = marker; self.shaderCache = shaderCache
    }
    func resolve(_ bookmark: Data) throws -> URL {
        var stale = false
        // A valid stale bookmark is refreshed by GameDataSession.select only after validation succeeds.
        return try URL(resolvingBookmarkData: bookmark, options: .withoutUI, relativeTo: nil, bookmarkDataIsStale: &stale)
    }
    func begin(_ url: URL) -> Bool {
        guard url.isFileURL else { return false }
        if url.startAccessingSecurityScopedResource() { scopes[url, default: 0] += 1; return true }
        let home = URL(fileURLWithPath: NSHomeDirectory()).standardizedFileURL.resolvingSymlinksInPath().path + "/"
        return url.standardizedFileURL.resolvingSymlinksInPath().path.hasPrefix(home) // App-owned folders need no security scope.
    }
    func end(_ url: URL) {
        guard let count = scopes[url], count > 0 else { return }
        url.stopAccessingSecurityScopedResource()
        if count == 1 { scopes.removeValue(forKey: url) } else { scopes[url] = count - 1 }
    }
    func bookmark(_ url: URL) throws -> Data {
        try url.bookmarkData(options: .minimalBookmark, includingResourceValuesForKeys: nil, relativeTo: nil)
    }
    func inspect(_ url: URL, full: Bool, progress: ((Int, Int) -> Void)?) throws -> GameDataLayout {
        try coordinate(url) { coordinated in
            try GameDataValidator.validate(root: coordinated, expected: expected, marker: marker, full: full, progress: progress, shaderCache: shaderCache)
        }
    }
    func coordinate<T>(_ url: URL, read: (URL) throws -> T) throws -> T {
        var failure: NSError?
        var result: Result<T, Error>?
        NSFileCoordinator(filePresenter: nil).coordinate(readingItemAt: url, options: .withoutChanges, error: &failure) { coordinated in
            result = Result { try read(coordinated) }
        }
        if let failure = failure { throw failure }
        guard let result = result else { throw GameDataError.unavailable }
        return try result.get()
    }
}

final class ExternalGameDataStore: ObservableObject {
    static let shared = ExternalGameDataStore()
    let enabled = (Bundle.main.object(forInfoDictionaryKey: "DMExternalGameData") as? Bool) == true
    @Published private(set) var ready = false
    @Published private(set) var busy = false
    @Published private(set) var imported = false
    @Published private(set) var folderName = "No folder selected"
    @Published private(set) var message = "Choose the exported game data folder."
    private(set) var started = false
    private let queue = DispatchQueue(label: "org.nxnative.external-game-data")
    private var session: GameDataSession?
    private var local: LocalGameData?
    private var shaderCacheParent: URL?
    private var restored = false
    private init() {
        guard enabled,
              let values = Bundle.main.object(forInfoDictionaryKey: "DMExternalDataIdentity") as? [String: String],
              let title = values["title_id"], let build = values["main_build"], let chain = values["shader_chain"], let inputs = values["shader_inputs"],
              let marker = Bundle.main.object(forInfoDictionaryKey: "DMExternalRomFSMarker") as? String else { return }
        let identity = GameDataIdentity(titleID: title, mainBuild: build, shaderChain: chain, shaderInputs: inputs)
        let digest = Bundle.main.object(forInfoDictionaryKey: "DMShaderCacheManifest") as? String
        guard let support = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first else { return }
        let cacheParent = support.appendingPathComponent("FFRSShaderCache", isDirectory: true)
        let cache = digest.map { ShaderCache(parent: cacheParent, manifestDigest: $0) }
        local = LocalGameData(root: support.appendingPathComponent("ImportedGameData", isDirectory: true))
        shaderCacheParent = cacheParent
        session = GameDataSession(access: ScopedGameDataAccess(expected: identity, marker: marker, shaderCache: cache), bookmarks: DefaultsGameDataBookmarks())
    }
    func restoreIfNeeded() {
        guard enabled, !restored else { return }; restored = true
        check(nil)
    }
    func choose(_ url: URL) { guard !started else { return }; check(url) }
    func recheck() { guard !started else { return }; check(nil) }
    private func check(_ selected: URL?) {
        guard !busy, let session = session else { return }
        busy = true; ready = false; message = "Checking game data..."
        queue.async {
            do {
                let progress: (Int, Int) -> Void = { checked, total in
                    DispatchQueue.main.async { self.message = "Preparing game data and local shaders: \(checked)/\(total)" }
                }
                let layout: GameDataLayout
                if let selected {
                    layout = try session.select(selected, progress: progress)
                } else if let local = self.local, let installed = try? session.useLocal(local.root) {
                    layout = installed
                } else {
                    layout = try session.restore(progress: progress)
                }
                DispatchQueue.main.async {
                    self.showReady(layout)
                }
            } catch {
                fputs("external data: \(error.localizedDescription)\n", stderr)
                DispatchQueue.main.async { self.message = error.localizedDescription; self.ready = false; self.busy = false }
            }
        }
    }
    private func showReady(_ layout: GameDataLayout) {
        imported = layout.root.resolvingSymlinksInPath().path == local?.root.resolvingSymlinksInPath().path
        folderName = imported ? "On this device" : layout.root.lastPathComponent
        message = imported ? "Game data ready for offline play" : "Game data ready"
        ready = true
        busy = false
    }
    func importAll() {
        guard ready, !busy, !started, let local, let session,
              let access = session.access as? ScopedGameDataAccess else { return }
        busy = true
        message = "Importing game data..."
        queue.async {
            do {
                guard let layout = session.current else { throw GameDataError.noSelection }
                if layout.root.resolvingSymlinksInPath().path != local.root.resolvingSymlinksInPath().path {
                    try access.coordinate(layout.root) { source in
                        let coordinated = GameDataLayout(root: source, cachedMSL: layout.cachedMSL)
                        try local.install(from: coordinated, progress: { count, total in
                            DispatchQueue.main.async { self.message = "Imported \(count)/\(total) files" }
                        }, validate: { url in
                            _ = try GameDataValidator.validate(root: url, expected: access.expected, marker: access.marker,
                                                               full: true, shaderCache: access.shaderCache)
                        })
                    }
                }
                let installed = try session.useLocal(local.root)
                DispatchQueue.main.async { self.showReady(installed) }
            } catch {
                DispatchQueue.main.async { self.message = error.localizedDescription; self.busy = false }
            }
        }
    }
    func clearData() {
        guard !busy, !started, let local, let session,
              let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first else { return }
        busy = true
        ready = false
        message = "Clearing game data..."
        let savePath = ProcessInfo.processInfo.environment["DM_SAVE"]
        queue.async {
            session.clearSelection()
            let result = Result {
                try local.clear(documents: documents, cache: self.shaderCacheParent, extraSavePath: savePath)
            }
            DispatchQueue.main.async {
                self.imported = false
                self.folderName = "No folder selected"
                switch result {
                case .success: self.message = "Game data cleared. Choose a folder to play again."
                case .failure(let error): self.message = error.localizedDescription
                }
                self.busy = false
            }
        }
    }
    func activate(_ completion: @escaping (Bool) -> Void) {
        if !enabled { completion(true); return }
        guard ready, !busy, !started, let session = session else { completion(false); return }
        busy = true
        queue.async {
            do {
                try session.start { layout in
                    if let temp = getenv("DM_TEMP") {
                        try FileManager.default.createDirectory(atPath: String(cString: temp), withIntermediateDirectories: true)
                    }
                    let paths: [String: String?] = ["DM_ROMFS": layout.romfs.path, "DM_MSL_DIR": layout.msl.path, "DM_AOC_DIR": layout.aoc?.path]
                    var previous: [String: String] = [:]
                    for key in paths.keys { if let value = getenv(key) { previous[key] = String(cString: value) } }
                    for (key, value) in paths {
                        let status = value.map { setenv(key, $0, 1) } ?? unsetenv(key)
                        if status != 0 {
                            for oldKey in paths.keys { if let value = previous[oldKey] { setenv(oldKey, value, 1) } else { unsetenv(oldKey) } }
                            throw GameDataError.environment
                        }
                    }
                }
                DispatchQueue.main.async { self.started = true; self.busy = false; completion(true) }
            } catch {
                fputs("external data launch: \(error.localizedDescription)\n", stderr)
                DispatchQueue.main.async { self.message = error.localizedDescription; self.ready = false; self.busy = false; completion(false) }
            }
        }
    }
}

struct GameDataFolderPicker: UIViewControllerRepresentable {
    let picked: (URL) -> Void
    let cancelled: () -> Void
    func makeCoordinator() -> Coordinator { Coordinator(picked: picked, cancelled: cancelled) }
    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.folder], asCopy: false)
        picker.allowsMultipleSelection = false; picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ uiViewController: UIDocumentPickerViewController, context: Context) {}
    final class Coordinator: NSObject, UIDocumentPickerDelegate {
        let picked: (URL) -> Void; let cancelled: () -> Void
        init(picked: @escaping (URL) -> Void, cancelled: @escaping () -> Void) { self.picked = picked; self.cancelled = cancelled }
        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            if let url = urls.first { picked(url) } else { cancelled() }
        }
        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) { cancelled() }
    }
}

@_cdecl("dm_external_data_configured")
public func dmExternalDataConfigured() -> Bool { ExternalGameDataStore.shared.started }
