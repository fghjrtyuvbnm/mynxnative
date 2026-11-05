import Foundation

@main enum GLShaderCacheTests {
    static func main() throws {
        let fm = FileManager.default
        let root = fm.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? fm.removeItem(at: root) }
        let id = GameDataIdentity(titleID: "gl-test", mainBuild: "build", shaderChain: "chain", shaderInputs: "inputs")
        let source = root.appendingPathComponent("external")
        let values = ["romfs/marker": Data([1,2]),
                      "msl/gl/inputs.tsv": Data("game\tgl-test\ninputs\tinputs\n".utf8),
                      "msl/gl/gl_shaders.tsv": Data("table".utf8),
                      "msl/gl/gl_shaders.metallib": Data([3,4,5])]
        let rows = values.sorted { $0.key < $1.key }.map {
            GameDataFile(path: $0.key, size: Int64($0.value.count), sha256: ShaderCache.digest($0.value))
        }
        var pack = Data("FFRSMSL1".utf8)
        for row in rows where row.path.hasPrefix("msl/") { pack.append(values[row.path]!) }
        try fm.createDirectory(at: source.appendingPathComponent("romfs"), withIntermediateDirectories: true)
        try values["romfs/marker"]!.write(to: source.appendingPathComponent("romfs/marker"))
        let manifest = try JSONEncoder().encode(GameDataManifest(formatVersion: 1, identity: id, files: rows))
        try manifest.write(to: source.appendingPathComponent("game-data.json"))
        try pack.write(to: source.appendingPathComponent("shaders.pack"))
        let parent = root.appendingPathComponent("cache")
        let cache = ShaderCache(parent: parent, manifestDigest: ShaderCache.digest(manifest))
        func validate(_ url: URL) throws -> GameDataLayout {
            try GameDataValidator.validate(root: url, expected: id, marker: "marker", full: true, shaderCache: cache)
        }
        let first: GameDataLayout
        do { first = try validate(source) }
        catch { fatalError("OpenGL packed data was rejected: \(error)") }
        let shader = try Data(contentsOf: first.msl.appendingPathComponent("gl/gl_shaders.metallib"))
        assert(shader == values["msl/gl/gl_shaders.metallib"])
        // Reject a manifest mixing graphics layouts, including when the
        // individual files and pack are otherwise complete and well hashed.
        let extraBytes = values["msl/gl/inputs.tsv"]!
        let mixedRows = rows + [GameDataFile(path: "msl/b-chain/inputs.tsv", size: Int64(extraBytes.count), sha256: ShaderCache.digest(extraBytes))]
        let mixed = try JSONEncoder().encode(GameDataManifest(formatVersion: 1, identity: id, files: mixedRows))
        try mixed.write(to: source.appendingPathComponent("game-data.json"))
        var mixedPack = pack
        mixedPack.append(extraBytes)
        try mixedPack.write(to: source.appendingPathComponent("shaders.pack"))
        let mixedCache = ShaderCache(parent: root.appendingPathComponent("mixed-cache"), manifestDigest: ShaderCache.digest(mixed))
        do {
            _ = try GameDataValidator.validate(root: source, expected: id, marker: "marker", full: true, shaderCache: mixedCache)
            fatalError("Mixed NVN and OpenGL shader layouts were accepted")
        } catch GameDataError.invalidManifest { }
        try manifest.write(to: source.appendingPathComponent("game-data.json"))
        try pack.write(to: source.appendingPathComponent("shaders.pack"))
        let local = LocalGameData(root: root.appendingPathComponent("support/ImportedGameData"))
        try local.install(from: first, validate: { _ = try validate($0) })
        try fm.moveItem(at: source, to: root.appendingPathComponent("disconnected"))
        try local.install(from: first, progress: { _,_ in fatalError("Duplicate GL import copied files") }, validate: { _ = try validate($0) })
        let offline = try validate(local.root)
        assert(offline.msl == first.msl)
        assert(!fm.fileExists(atPath: local.root.appendingPathComponent("msl").path))
        let docs = root.appendingPathComponent("Documents")
        try fm.createDirectory(at: docs.appendingPathComponent("save"), withIntermediateDirectories: true)
        try Data([6]).write(to: docs.appendingPathComponent("save/file"))
        try Data([7]).write(to: docs.appendingPathComponent("env.txt"))
        try local.clear(documents: docs, cache: parent, extraSavePath: nil)
        assert(fm.fileExists(atPath: docs.appendingPathComponent("save/file").path))
        assert(fm.fileExists(atPath: docs.appendingPathComponent("env.txt").path))
        assert(!fm.fileExists(atPath: parent.path))
        print("PASS: OpenGL packed shader import, reuse, offline access and save-preserving clear")
    }
}
