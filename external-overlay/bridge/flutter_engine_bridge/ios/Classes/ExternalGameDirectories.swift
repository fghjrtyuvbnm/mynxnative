import Flutter
import Foundation
import UIKit
import UniformTypeIdentifiers

/// Retains the directory grants while the native engine reads game files.
final class ExternalGameDirectories: NSObject, UIDocumentPickerDelegate,
  UIAdaptivePresentationControllerDelegate {
  private struct Lease {
    let url: URL
    let scoped: Bool
  }

  private let queue = DispatchQueue(label: "org.krkr2.external-game-directories")
  private let defaults = UserDefaults.standard
  private let key = "krkr2.external-directory-bookmarks.v1"
  private var leases: [String: Lease] = [:]
  private var pending: FlutterResult?

  deinit {
    for lease in leases.values where lease.scoped {
      lease.url.stopAccessingSecurityScopedResource()
    }
  }

  func pick(from presenter: UIViewController?, result: @escaping FlutterResult) {
    guard pending == nil else {
      result(FlutterError(code: "picker_busy", message: "A folder picker is already open.", details: nil))
      return
    }
    guard let presenter else {
      result(FlutterError(code: "no_presenter", message: "The folder picker is unavailable.", details: nil))
      return
    }
    pending = result
    let picker = UIDocumentPickerViewController(forOpeningContentTypes: [.folder], asCopy: false)
    picker.delegate = self
    picker.allowsMultipleSelection = false
    picker.shouldShowFileExtensions = true
    presenter.present(picker, animated: true)
    picker.presentationController?.delegate = self
  }

  private func finish(_ value: Any?) {
    let callback = pending
    pending = nil
    callback?(value)
  }

  func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
    finish(nil)
  }

  func presentationControllerDidDismiss(_ presentationController: UIPresentationController) {
    finish(nil)
  }

  func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
    guard let url = urls.first else {
      finish(nil)
      return
    }
    queue.async {
      do {
        let path = url.standardizedFileURL.path
        var bookmarks = self.defaults.dictionary(forKey: self.key) as? [String: Data] ?? [:]
        let existing = bookmarks.first { entry in
          var stale = false
          return (try? URL(resolvingBookmarkData: entry.value, options: [],
            relativeTo: nil, bookmarkDataIsStale: &stale).standardizedFileURL.path) == path
        }
        let id = existing?.key ?? UUID().uuidString
        let scoped = url.startAccessingSecurityScopedResource()
        do {
          try self.checkDirectory(url)
          let bookmark = try url.bookmarkData(options: .minimalBookmark,
            includingResourceValuesForKeys: nil, relativeTo: nil)
          bookmarks[id] = bookmark
          self.defaults.set(bookmarks, forKey: self.key)
          self.replaceLease(id, url: url, scoped: scoped)
          DispatchQueue.main.async { self.finish(["id": id, "path": path]) }
        } catch {
          if scoped { url.stopAccessingSecurityScopedResource() }
          throw error
        }
      } catch {
        DispatchQueue.main.async {
          self.finish(FlutterError(code: "directory_unavailable",
            message: error.localizedDescription, details: nil))
        }
      }
    }
  }

  private func checkDirectory(_ url: URL) throws {
    var coordinatorError: NSError?
    var values: URLResourceValues?
    var readError: Error?
    NSFileCoordinator().coordinate(readingItemAt: url, options: .withoutChanges,
      error: &coordinatorError) { coordinatedURL in
        do {
          values = try coordinatedURL.resourceValues(forKeys: [.isDirectoryKey])
        } catch {
          readError = error
        }
      }
    if let error = coordinatorError ?? (readError as NSError?) { throw error }
    guard values?.isDirectory == true,
      FileManager.default.isReadableFile(atPath: url.path) else {
      throw NSError(domain: NSCocoaErrorDomain, code: NSFileReadNoSuchFileError,
        userInfo: [NSLocalizedDescriptionKey: "Reconnect the storage device or select the game folder again."])
    }
  }

  private func replaceLease(_ id: String, url: URL, scoped: Bool) {
    if let old = leases.updateValue(Lease(url: url, scoped: scoped), forKey: id), old.scoped {
      old.url.stopAccessingSecurityScopedResource()
    }
  }

  private func activate(_ id: String) throws -> String {
    var bookmarks = defaults.dictionary(forKey: key) as? [String: Data] ?? [:]
    guard let bookmark = bookmarks[id] else {
      throw NSError(domain: NSCocoaErrorDomain, code: NSFileReadNoPermissionError,
        userInfo: [NSLocalizedDescriptionKey: "Select this external game folder again."])
    }
    var stale = false
    let url = try URL(resolvingBookmarkData: bookmark, options: [],
      relativeTo: nil, bookmarkDataIsStale: &stale)
    let scoped = url.startAccessingSecurityScopedResource()
    do {
      try checkDirectory(url)
      if stale {
        bookmarks[id] = try url.bookmarkData(options: .minimalBookmark,
          includingResourceValuesForKeys: nil, relativeTo: nil)
        defaults.set(bookmarks, forKey: key)
      }
      replaceLease(id, url: url, scoped: scoped)
      return url.standardizedFileURL.path
    } catch {
      if scoped { url.stopAccessingSecurityScopedResource() }
      throw error
    }
  }

  func restore(_ ids: [String], result: @escaping FlutterResult) {
    queue.async {
      let resolved = ids.compactMap { id -> [String: String]? in
        guard let path = try? self.activate(id) else { return nil }
        return ["id": id, "path": path]
      }
      DispatchQueue.main.async { result(resolved) }
    }
  }

  func activate(_ id: String, result: @escaping FlutterResult) {
    queue.async {
      do {
        let path = try self.activate(id)
        DispatchQueue.main.async { result(path) }
      } catch {
        DispatchQueue.main.async {
          result(FlutterError(code: "directory_unavailable",
            message: error.localizedDescription, details: nil))
        }
      }
    }
  }

  func forget(_ id: String, result: @escaping FlutterResult) {
    queue.async {
      var bookmarks = self.defaults.dictionary(forKey: self.key) as? [String: Data] ?? [:]
      bookmarks.removeValue(forKey: id)
      self.defaults.set(bookmarks, forKey: self.key)
      if let lease = self.leases.removeValue(forKey: id), lease.scoped {
        lease.url.stopAccessingSecurityScopedResource()
      }
      DispatchQueue.main.async { result(nil) }
    }
  }
}

