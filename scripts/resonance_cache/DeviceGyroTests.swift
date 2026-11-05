import Foundation

@main enum DeviceGyroTests {
    static func main() throws {
        let file = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
        let rows = try JSONDecoder().decode(SettingsFile.self, from: file).settings
        let suite = "device-motion-test-" + UUID().uuidString
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite); unsetenv("DM_PHONE_MOTION") }
        let model = LauncherModel(rows, defaults: defaults)
        let toggle = rows.first { $0.env == "DM_PHONE_MOTION" }!
        assert(toggle.onValue == "1" && toggle.offValue == "auto" && toggle.basic)
        assert(model.values[toggle.env] == "1")
        model.apply()
        assert(String(cString: getenv(toggle.env)) == "1")
        model.values[toggle.env] = toggle.offValue
        model.apply()
        assert(String(cString: getenv(toggle.env)) == "auto")
        assert(defaults.string(forKey: "launcher." + toggle.env) == "auto")
        let restored = LauncherModel(rows, defaults: defaults)
        assert(restored.values[toggle.env] == "auto")
        restored.reset(); restored.apply()
        assert(String(cString: getenv(toggle.env)) == "1")
        assert(defaults.object(forKey: "launcher." + toggle.env) == nil)
        print("PASS: device gyro default, automatic selection, persistence and reset")
    }
}
