// Portable directory identity, validation, bookmark and launch lifecycle contracts.
import Foundation

struct GameDataIdentity: Codable, Equatable {
    let titleID, mainBuild, shaderChain, shaderInputs: String
    enum CodingKeys: String, CodingKey {
        case titleID = "title_id", mainBuild = "main_build", shaderChain = "shader_chain", shaderInputs = "shader_inputs"
    }
}
struct GameDataFile: Codable { let path: String; let size: Int64; let sha256: String }
struct GameDataManifest: Codable {
    let formatVersion: Int
    let identity: GameDataIdentity
    let files: [GameDataFile]
    enum CodingKeys: String, CodingKey { case formatVersion = "format_version", identity, files }

    func shaderPrefix() throws -> String {
        let candidates = ["msl/b-\(identity.shaderChain)/", "msl/gl/"]
        let matches = candidates.filter { prefix in files.contains { $0.path == prefix + "inputs.tsv" } }
        guard matches.count == 1, files.allSatisfy({ !$0.path.hasPrefix("msl/") || $0.path.hasPrefix(matches[0]) }) else {
            throw GameDataError.invalidManifest
        }
        return matches[0]
    }
}
struct GameDataLayout {
    let root: URL
    var romfs: URL {
        let image = root.appendingPathComponent("romfs.img")
        return FileManager.default.fileExists(atPath: image.path) ? image : root.appendingPathComponent("romfs", isDirectory: true)
    }
    var cachedMSL: URL? = nil
    var msl: URL { cachedMSL ?? root.appendingPathComponent("msl", isDirectory: true) }
    var aoc: URL? {
        let path = root.appendingPathComponent("aoc", isDirectory: true)
        var directory: ObjCBool = false
        return FileManager.default.fileExists(atPath: path.path, isDirectory: &directory) && directory.boolValue ? path : nil
    }
}
enum GameDataError: Error, LocalizedError {
    case noSelection, permission, wrongBuild, invalidManifest, missingFile(String), unsafePath, alreadyStarted, unavailable, environment, cacheSpace, cacheIntegrity(String)
    var errorDescription: String? {
        switch self {
        case .noSelection: return "Choose the exported game data folder."
        case .permission: return "Folder access is unavailable. Connect the drive and choose the folder again."
        case .wrongBuild: return "This data folder belongs to another game build. Choose the matching exported folder."
        case .invalidManifest: return "The game data folder is incomplete or its manifest cannot be read."
        case .missingFile(let name): return "A game data file is missing or incomplete: \(name)"
        case .unsafePath: return "The data folder contains an unsupported file path."
        case .alreadyStarted: return "The data folder cannot change while the game is running."
        case .unavailable: return "The game data folder is unavailable. Connect the drive or choose another folder."
        case .cacheSpace: return "Free at least 4 GB of device storage, then choose the data folder again."
        case .cacheIntegrity(let name): return "Shader verification failed: \(name). Restore it on the drive and try again."
        case .environment: return "The game could not prepare its data paths. Try again."
        }
    }
}

enum GameDataValidator {
    static func safePath(_ path: String) -> Bool {
        if path == "romfs.img" { return true }
        let parts = path.split(separator: "/", omittingEmptySubsequences: false)
        return !parts.isEmpty && ["romfs", "msl", "aoc"].contains(String(parts[0])) &&
            !path.contains("\\") && !path.contains(":") && !parts.contains("..") && !parts.contains(".") && !parts.contains("")
    }
    static func validate(root: URL, expected: GameDataIdentity, marker: String, full: Bool,
                         progress: ((Int, Int) -> Void)? = nil,
                         shaderCache: ShaderCache? = nil) throws -> GameDataLayout {
        guard root.isFileURL else { throw GameDataError.unsafePath }
        var directory: ObjCBool = false
        guard FileManager.default.fileExists(atPath: root.path, isDirectory: &directory), directory.boolValue else { throw GameDataError.unavailable }
        let manifestURL = root.appendingPathComponent("game-data.json")
        let base = root.standardizedFileURL.resolvingSymlinksInPath().path + "/"
        guard manifestURL.resolvingSymlinksInPath().path.hasPrefix(base),
              let manifestAttrs = try? FileManager.default.attributesOfItem(atPath: manifestURL.path),
              manifestAttrs[.type] as? FileAttributeType == .typeRegular,
              let manifestSize = (manifestAttrs[.size] as? NSNumber)?.int64Value,
              manifestSize >= 0, manifestSize <= 128 * 1024 * 1024 else { throw GameDataError.invalidManifest }
        let data: Data
        do { data = try Data(contentsOf: manifestURL) } catch { throw GameDataError.invalidManifest }
        guard data.count <= 128 * 1024 * 1024,
              let manifest = try? JSONDecoder().decode(GameDataManifest.self, from: data), manifest.formatVersion == 1 else { throw GameDataError.invalidManifest }
        if let cache = shaderCache, ShaderCache.digest(data) != cache.manifestDigest { throw GameDataError.wrongBuild }
        guard manifest.identity == expected else { throw GameDataError.wrongBuild }
        let romfsMarker = "romfs/" + marker
        let stamp = try manifest.shaderPrefix() + "inputs.tsv"
        let names = Set(manifest.files.map(\.path))
        let image = names.contains("romfs.img")
        guard names.count == manifest.files.count, names.contains(stamp),
              image ? !names.contains(where: { $0.hasPrefix("romfs/") }) : names.contains(romfsMarker),
              image || !FileManager.default.fileExists(atPath: root.appendingPathComponent("romfs.img").path)
        else { throw GameDataError.invalidManifest }
        let check = manifest.files.filter {
            shaderCache != nil ? !$0.path.hasPrefix("msl/") : (full || $0.path == "romfs.img" || $0.path.hasPrefix("romfs/") || $0.path == stamp)
        }
        for (index, record) in check.enumerated() {
            guard safePath(record.path), record.size >= 0, record.sha256.count == 64 else { throw GameDataError.unsafePath }
            let path = root.appendingPathComponent(record.path).standardizedFileURL.resolvingSymlinksInPath()
            guard path.path.hasPrefix(base) else { throw GameDataError.unsafePath }
            guard let attrs = try? FileManager.default.attributesOfItem(atPath: path.path),
                  attrs[.type] as? FileAttributeType == .typeRegular,
                  (attrs[.size] as? NSNumber)?.int64Value == record.size else { throw GameDataError.missingFile(URL(fileURLWithPath: record.path).lastPathComponent) }
            if index % 256 == 0 || index + 1 == check.count { progress?(index + 1, check.count) }
        }
        let local = try shaderCache?.prepare(source: root, manifest: manifest, progress: progress)
        let stampURL = local?.appendingPathComponent(String(stamp.dropFirst(4))) ?? root.appendingPathComponent(stamp)
        let contents = (try? String(contentsOf: stampURL, encoding: .utf8)) ?? ""
        let rows = Set(contents.components(separatedBy: .newlines))
        guard rows.contains("game\t\(expected.titleID)"), rows.contains("inputs\t\(expected.shaderInputs)") else { throw GameDataError.wrongBuild }
        return GameDataLayout(root: root, cachedMSL: local)
    }
}

protocol GameDataAccess {
    func resolve(_ bookmark: Data) throws -> URL
    func begin(_ url: URL) -> Bool
    func end(_ url: URL)
    func bookmark(_ url: URL) throws -> Data
    func inspect(_ url: URL, full: Bool, progress: ((Int, Int) -> Void)?) throws -> GameDataLayout
}
protocol GameDataBookmarks {
    func read() -> Data?
    func write(_ data: Data) throws
    func clear()
}

// All methods run on one serial queue. A successful scope is retained until replacement or process teardown.
final class GameDataSession {
    let access: GameDataAccess
    let bookmarks: GameDataBookmarks
    private(set) var current: GameDataLayout?
    private var grantedURL: URL?
    private(set) var started = false
    init(access: GameDataAccess, bookmarks: GameDataBookmarks) { self.access = access; self.bookmarks = bookmarks }
    deinit { if let url = grantedURL { access.end(url) } }
    func restore(progress: ((Int, Int) -> Void)? = nil) throws -> GameDataLayout {
        guard let bookmark = bookmarks.read() else { throw GameDataError.noSelection }
        return try select(access.resolve(bookmark), progress: progress)
    }
    func useLocal(_ url: URL) throws -> GameDataLayout {
        guard !started else { throw GameDataError.alreadyStarted }
        guard access.begin(url) else { throw GameDataError.permission }
        do {
            let layout = try access.inspect(url, full: true, progress: nil)
            if let previous = grantedURL { access.end(previous) }
            current = layout
            grantedURL = url
            return layout
        } catch { access.end(url); throw error }
    }
    func clearSelection() {
        if let url = grantedURL { access.end(url) }
        current = nil
        grantedURL = nil
        bookmarks.clear()
    }
    func select(_ url: URL, progress: ((Int, Int) -> Void)? = nil) throws -> GameDataLayout {
        guard !started else { throw GameDataError.alreadyStarted }
        guard access.begin(url) else { throw GameDataError.permission }
        do {
            let layout = try access.inspect(url, full: true, progress: progress)
            let bookmark = try access.bookmark(url)
            try bookmarks.write(bookmark) // Failed replacement never discards the previous remembered folder.
            let previous = grantedURL
            current = layout
            grantedURL = url
            if let previous = previous { access.end(previous) }
            return layout
        } catch { access.end(url); throw error }
    }
    func start(apply: (GameDataLayout) throws -> Void) throws {
        guard !started else { throw GameDataError.alreadyStarted }
        guard let grantedURL = grantedURL else { throw GameDataError.noSelection }
        let fresh = try access.inspect(grantedURL, full: false, progress: nil)
        try apply(fresh)
        started = true
    }
}

/// The validated source stays open while its manifest-listed files are installed.
/// Packed shaders already verified in Application Support are shared with offline play.
struct LocalGameData {
    let root: URL
    private var stage: URL { root.deletingLastPathComponent().appendingPathComponent(".ImportedGameData.partial") }
    private let fm = FileManager.default

    func install(from layout: GameDataLayout, progress: ((Int, Int) -> Void)? = nil,
                 validate: (URL) throws -> Void) throws {
        if fm.fileExists(atPath: root.path), (try? validate(root)) != nil { return }
        if fm.fileExists(atPath: stage.path) { try fm.removeItem(at: stage) }
        try fm.createDirectory(at: stage, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: stage) }
        var scratch = stage
        var settings = URLResourceValues()
        settings.isExcludedFromBackup = true
        try scratch.setResourceValues(settings)
        let manifest = try Data(contentsOf: layout.root.appendingPathComponent("game-data.json"))
        let data = try JSONDecoder().decode(GameDataManifest.self, from: manifest)
        let rows = data.files.filter { layout.cachedMSL == nil || !$0.path.hasPrefix("msl/") }
        let base = layout.root.resolvingSymlinksInPath().standardizedFileURL.path + "/"
        var seen = Set<String>()
        for (index, record) in rows.enumerated() {
            guard GameDataValidator.safePath(record.path), seen.insert(record.path).inserted else {
                throw GameDataError.unsafePath
            }
            let source = layout.root.appendingPathComponent(record.path).resolvingSymlinksInPath().standardizedFileURL
            guard source.path.hasPrefix(base),
                  let attrs = try? fm.attributesOfItem(atPath: source.path),
                  attrs[.type] as? FileAttributeType == .typeRegular,
                  (attrs[.size] as? NSNumber)?.int64Value == record.size else {
                throw GameDataError.missingFile(record.path)
            }
            let destination = stage.appendingPathComponent(record.path)
            try fm.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            try fm.copyItem(at: source, to: destination)
            guard try ShaderCache.digest(file: destination) == record.sha256 else {
                throw GameDataError.cacheIntegrity(record.path)
            }
            progress?(index + 1, rows.count)
        }
        try manifest.write(to: stage.appendingPathComponent("game-data.json"))
        try validate(stage)
        if fm.fileExists(atPath: root.path) { try fm.removeItem(at: root) }
        try fm.moveItem(at: stage, to: root)
    }

    func clear(documents: URL, cache: URL?, extraSavePath: String?) throws {
        // A LiveContainer host may expose a parent Documents directory. Never
        // sweep unknown entries there, including other apps or containers.
        let generated: Set<String> = ["romfs", "romfs.img", "aoc", "msl", "temp",
                                      "log.txt", "log.prev.txt", "gpu_captures", "pso",
                                      "pso_user.tsv", "pso_archive"]
        let legacy = try fm.contentsOfDirectory(at: documents, includingPropertiesForKeys: nil)
            .filter { generated.contains($0.lastPathComponent.lowercased()) }
        let save = extraSavePath.map { URL(fileURLWithPath: $0).resolvingSymlinksInPath().standardizedFileURL.path }
        for url in [root, stage] + [cache].compactMap({ $0 }) + legacy where fm.fileExists(atPath: url.path) {
            let path = url.resolvingSymlinksInPath().standardizedFileURL.path
            if let save, save == path || save.hasPrefix(path + "/") { continue }
            try fm.removeItem(at: url)
        }
    }
}
