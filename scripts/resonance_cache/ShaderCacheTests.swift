import Foundation

private final class TestBookmarks: GameDataBookmarks {
    var data: Data? = Data([1])
    func read() -> Data? { data }
    func write(_ data: Data) { self.data = data }
    func clear() { data = nil }
}

private struct TestAccess: GameDataAccess {
    let validate: (URL) throws -> GameDataLayout
    func resolve(_ bookmark: Data) throws -> URL { throw GameDataError.unavailable }
    func begin(_ url: URL) -> Bool { true }
    func end(_ url: URL) {}
    func bookmark(_ url: URL) throws -> Data { Data([1]) }
    func inspect(_ url: URL, full: Bool, progress: ((Int, Int) -> Void)?) throws -> GameDataLayout {
        try validate(url)
    }
}

@main enum CacheTests {
    static func main() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? fm.removeItem(at: root) }
        let source = root.appendingPathComponent("external")
        let parent = root.appendingPathComponent("local")
        let id = GameDataIdentity(titleID: "test", mainBuild: "main", shaderChain: "chain", shaderInputs: "inputs")
        let stamp = "msl/b-chain/inputs.tsv"
        let shader = "msl/b-chain/example_b.metallib"
        let marker = "Game/marker"
        let originals = [stamp: Data("game\ttest\ninputs\tinputs\n".utf8), shader: Data([1,2,3]), "romfs/"+marker: Data([4]), "aoc/1.img": Data([5])]
        for (path, bytes) in originals {
            let file = source.appendingPathComponent(path)
            try fm.createDirectory(at: file.deletingLastPathComponent(), withIntermediateDirectories: true)
            try bytes.write(to: file)
        }
        let rows = originals.sorted { $0.key < $1.key }.map {
            GameDataFile(path: $0.key, size: Int64($0.value.count), sha256: ShaderCache.digest($0.value))
        }
        let manifest = try JSONEncoder().encode(GameDataManifest(formatVersion: 1, identity: id, files: rows))
        try manifest.write(to: source.appendingPathComponent("game-data.json"))
        let hash = ShaderCache.digest(manifest)
        let cache = ShaderCache(parent: parent, manifestDigest: hash)
        func inspect() throws -> GameDataLayout {
            try GameDataValidator.validate(root: source, expected: id, marker: marker, full: true, shaderCache: cache)
        }
        try Data([9,9,9]).write(to: source.appendingPathComponent(shader))
        do { _ = try inspect(); fatalError("Same-length corrupt shader was accepted") }
        catch GameDataError.cacheIntegrity(_) { }
        assert(!fm.fileExists(atPath: parent.appendingPathComponent(hash).path))
        assert(!fm.fileExists(atPath: parent.appendingPathComponent(".\(hash).partial").path))
        // Simulate an app killed between creating its temporary directory and committing.
        try fm.createDirectory(at: parent.appendingPathComponent(".\(hash).partial"), withIntermediateDirectories: false)
        try originals[shader]!.write(to: source.appendingPathComponent(shader))
        let first = try inspect()
        assert(first.msl.path.hasPrefix(parent.path + "/"))
        assert(first.romfs.path.hasPrefix(source.path + "/"))
        try fm.removeItem(at: source.appendingPathComponent("msl"))
        let next = try inspect()
        assert(next.msl == first.msl)
        let cached = try Data(contentsOf: next.msl.appendingPathComponent("b-chain/example_b.metallib"))
        assert(cached == originals[shader])
        try fm.removeItem(at: first.msl.deletingLastPathComponent())
        var packed = Data("FFRSMSL1".utf8)
        for row in rows where row.path.hasPrefix("msl/") { packed.append(originals[row.path]!) }
        let archive = source.appendingPathComponent("shaders.pack")
        var damaged = packed
        damaged[damaged.count - 1] ^= 1
        try damaged.write(to: archive)
        do { _ = try inspect(); fatalError("Corrupt packed shader was accepted") }
        catch GameDataError.cacheIntegrity(_) { }
        try packed.write(to: archive)
        let fromPack = try inspect()
        let packedShader = try Data(contentsOf: fromPack.msl.appendingPathComponent("b-chain/example_b.metallib"))
        assert(packedShader == originals[shader])
        let local = LocalGameData(root: root.appendingPathComponent("support/ImportedGameData"))
        func validate(_ url: URL) throws -> GameDataLayout {
            try GameDataValidator.validate(root: url, expected: id, marker: marker, full: true, shaderCache: cache)
        }
        let resource = source.appendingPathComponent("romfs/" + marker)
        try Data([0]).write(to: resource)
        do {
            try local.install(from: fromPack, validate: { _ = try validate($0) })
            fatalError("Same-length corrupt game data was imported")
        } catch GameDataError.cacheIntegrity(_) {}
        assert(!fm.fileExists(atPath: local.root.path))
        try originals["romfs/" + marker]!.write(to: resource)
        try local.install(from: fromPack, validate: { _ = try validate($0) })
        try fm.moveItem(at: source, to: root.appendingPathComponent("disconnected"))
        try local.install(from: fromPack, progress: { _, _ in fatalError("Import copied duplicate files") },
                          validate: { _ = try validate($0) })
        let bookmarks = TestBookmarks()
        let session = GameDataSession(access: TestAccess(validate: validate), bookmarks: bookmarks)
        let offline = try session.useLocal(local.root)
        assert(offline.msl == fromPack.msl)
        assert(!fm.fileExists(atPath: local.root.appendingPathComponent("msl").path))
        assert(fm.fileExists(atPath: offline.aoc!.appendingPathComponent("1.img").path))
        let playing = GameDataSession(access: TestAccess(validate: validate), bookmarks: bookmarks)
        _ = try playing.useLocal(local.root)
        try playing.start { assert($0.root == local.root) }
        let docs = root.appendingPathComponent("Documents")
        try fm.createDirectory(at: docs.appendingPathComponent("save"), withIntermediateDirectories: true)
        try Data([6]).write(to: docs.appendingPathComponent("save/file"))
        try Data([7]).write(to: docs.appendingPathComponent("env.txt"))
        try Data([8]).write(to: docs.appendingPathComponent("log.txt"))
        session.clearSelection()
        try local.clear(documents: docs, cache: parent, extraSavePath: nil)
        assert(session.current == nil && bookmarks.read() == nil)
        assert(!fm.fileExists(atPath: local.root.path) && !fm.fileExists(atPath: parent.path))
        assert(!fm.fileExists(atPath: docs.appendingPathComponent("log.txt").path))
        assert(fm.fileExists(atPath: docs.appendingPathComponent("save/file").path))
        assert(fm.fileExists(atPath: docs.appendingPathComponent("env.txt").path))
        assert(fm.fileExists(atPath: root.appendingPathComponent("disconnected/aoc/1.img").path))
        print("PASS: full import, offline launch, reuse, and save-preserving clear")
        print("PASS: failed copy, stale partial recovery, atomic commit and reuse with external ROMFS")
    }
}

