import Foundation
import CryptoKit

/// Application Support keeps verified shaders across launches and avoids purgeable cache storage.
struct ShaderCache {
    let parent: URL
    let manifestDigest: String
    private let fm = FileManager.default

    static func digest(_ bytes: Data) -> String {
        SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
    }

    static func digest(file: URL) throws -> String {
        let stream = try FileHandle(forReadingFrom: file)
        defer { try? stream.close() }
        var hash = SHA256()
        while let block = try stream.read(upToCount: 1024 * 1024), !block.isEmpty {
            hash.update(data: block)
        }
        return hash.finalize().map { String(format: "%02x", $0) }.joined()
    }

    func prepare(source: URL, manifest: GameDataManifest, progress: ((Int, Int) -> Void)?) throws -> URL {
        guard manifestDigest.count == 64, manifestDigest.allSatisfy({ $0.isASCII && $0.isHexDigit }) else {
            throw GameDataError.invalidManifest
        }
        var cacheRoot = parent
        try fm.createDirectory(at: cacheRoot, withIntermediateDirectories: true)
        var settings = URLResourceValues()
        settings.isExcludedFromBackup = true
        try cacheRoot.setResourceValues(settings)
        let final = cacheRoot.appendingPathComponent(manifestDigest, isDirectory: true)
        let stage = cacheRoot.appendingPathComponent(".\(manifestDigest).partial", isDirectory: true)
        let receiptName = "verified-manifest.sha256"
        let receipt = Data(manifestDigest.utf8)
        let stamp = "msl/b-\(manifest.identity.shaderChain)/inputs.tsv"
        let rows = manifest.files.filter { $0.path.hasPrefix("msl/") }
        guard let stampRow = rows.first(where: { $0.path == stamp }), rows.count > 1 else {
            throw GameDataError.invalidManifest
        }
        if (try? Data(contentsOf: final.appendingPathComponent(receiptName))) == receipt,
           let bytes = try? Data(contentsOf: final.appendingPathComponent(stamp)),
           Self.digest(bytes) == stampRow.sha256 {
            return final.appendingPathComponent("msl", isDirectory: true)
        }
        if fm.fileExists(atPath: stage.path) { try fm.removeItem(at: stage) }
        if fm.fileExists(atPath: final.path) { try fm.removeItem(at: final) }
        var total: Int64 = 0
        for row in rows {
            guard GameDataValidator.safePath(row.path), row.path.hasPrefix("msl/b-\(manifest.identity.shaderChain)/"),
                  row.size >= 0, row.size <= 16 * 1024 * 1024, row.sha256.count == 64 else {
                throw GameDataError.invalidManifest
            }
            total += row.size
        }
        if let attrs = try? fm.attributesOfFileSystem(forPath: cacheRoot.path),
           let free = attrs[.systemFreeSize] as? NSNumber,
           free.int64Value < total + 512 * 1024 * 1024 {
            throw GameDataError.cacheSpace
        }
        try fm.createDirectory(at: stage, withIntermediateDirectories: false)
        var committed = false
        defer { if !committed { try? fm.removeItem(at: stage) } }
        let base = source.standardizedFileURL.resolvingSymlinksInPath().path + "/"
        let packed = source.appendingPathComponent("shaders.pack").resolvingSymlinksInPath()
        let archive: FileHandle?
        if fm.fileExists(atPath: packed.path) {
            guard packed.path.hasPrefix(base),
                  let attrs = try? fm.attributesOfItem(atPath: packed.path),
                  attrs[.type] as? FileAttributeType == .typeRegular,
                  (attrs[.size] as? NSNumber)?.int64Value == total + 8 else {
                throw GameDataError.invalidManifest
            }
            archive = try FileHandle(forReadingFrom: packed)
        } else {
            archive = nil
        }
        defer { try? archive?.close() }
        if let archive, try archive.read(upToCount: 8) != Data("FFRSMSL1".utf8) {
            throw GameDataError.invalidManifest
        }
        var directories = Set<URL>()
        progress?(0, rows.count)
        for (index, row) in rows.enumerated() {
            let name = URL(fileURLWithPath: row.path).lastPathComponent
            let bytes: Data
            if let archive {
                bytes = row.size == 0 ? Data() : (try archive.read(upToCount: Int(row.size)) ?? Data())
            } else {
                let incoming = source.appendingPathComponent(row.path).standardizedFileURL.resolvingSymlinksInPath()
                guard incoming.path.hasPrefix(base) else { throw GameDataError.unsafePath }
                guard let attrs = try? fm.attributesOfItem(atPath: incoming.path),
                      attrs[.type] as? FileAttributeType == .typeRegular,
                      (attrs[.size] as? NSNumber)?.int64Value == row.size else {
                    throw GameDataError.missingFile(incoming.lastPathComponent)
                }
                bytes = try Data(contentsOf: incoming)
            }
            guard bytes.count == row.size, Self.digest(bytes) == row.sha256 else {
                throw GameDataError.cacheIntegrity(name)
            }
            let output = stage.appendingPathComponent(row.path)
            let dir = output.deletingLastPathComponent()
            if directories.insert(dir).inserted { try fm.createDirectory(at: dir, withIntermediateDirectories: true) }
            try bytes.write(to: output)
            if index % 256 == 0 || index + 1 == rows.count { progress?(index + 1, rows.count) }
        }
        try receipt.write(to: stage.appendingPathComponent(receiptName), options: .atomic)
        try fm.moveItem(at: stage, to: final)
        committed = true
        return final.appendingPathComponent("msl", isDirectory: true)
    }
}
