import Foundation

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
        let originals = [stamp: Data("game\ttest\ninputs\tinputs\n".utf8), shader: Data([1,2,3]), "romfs/"+marker: Data([4])]
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
        print("PASS: failed copy, stale partial recovery, atomic commit and reuse with external ROMFS")
    }
}

