import Cocoa
import WebKit
import UniformTypeIdentifiers

final class KENNDesktopCompanion: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate {
    private let kennURL = URL(string: "http://127.0.0.1:8090/")!
    private var window: NSWindow!
    private var webView: WKWebView!
    private var statusItem: NSToolbarItem!
    private var serverProcess: Process?
    private var automixWorkerProcess: Process?
    private var healthTimer: Timer?
    private var repositoryRoot: URL?

    func applicationDidFinishLaunching(_ notification: Notification) {
        repositoryRoot = findRepositoryRoot()
        createWindow()
        startOrConnect()
        healthTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.refreshHealth()
        }
    }

    func applicationWillTerminate(_ notification: Notification) {
        healthTimer?.invalidate()
        if let process = serverProcess, process.isRunning {
            process.terminate()
        }
        if let process = automixWorkerProcess, process.isRunning {
            process.terminate()
        }
    }

    private func createWindow() {
        let configuration = WKWebViewConfiguration()
        configuration.preferences.isElementFullscreenEnabled = true
        webView = WKWebView(frame: .zero, configuration: configuration)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.allowsBackForwardNavigationGestures = true

        window = NSWindow(
            contentRect: NSRect(x: 0, y: 0, width: 1440, height: 940),
            styleMask: [.titled, .closable, .miniaturizable, .resizable],
            backing: .buffered,
            defer: false
        )
        window.title = "KENN Desktop Companion"
        window.minSize = NSSize(width: 960, height: 650)
        window.center()
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)

        let toolbar = NSToolbar(identifier: "KENNToolbar")
        toolbar.delegate = self
        toolbar.displayMode = .iconAndLabel
        window.toolbar = toolbar
    }

    private func findRepositoryRoot() -> URL? {
        let environment = ProcessInfo.processInfo.environment
        if let value = environment["KENN_REPO_ROOT"], isRepository(URL(fileURLWithPath: value)) {
            return URL(fileURLWithPath: value)
        }
        if let argument = CommandLine.arguments.dropFirst().first,
           argument.hasPrefix("--repo-root="),
           isRepository(URL(fileURLWithPath: String(argument.dropFirst("--repo-root=".count)))) {
            return URL(fileURLWithPath: String(argument.dropFirst("--repo-root=".count)))
        }

        var candidate = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        for _ in 0..<8 {
            if isRepository(candidate) { return candidate }
            candidate.deleteLastPathComponent()
        }
        candidate = Bundle.main.bundleURL
        for _ in 0..<8 {
            if isRepository(candidate) { return candidate }
            candidate.deleteLastPathComponent()
        }
        return nil
    }

    private func isRepository(_ url: URL) -> Bool {
        serverScript(in: url) != nil
    }

    private func serverScript(in root: URL) -> URL? {
        let candidates = [
            root.appendingPathComponent("apps/backend/src/kenn/server.py"),
            root.appendingPathComponent("runtime/legacy/kenn/server.py")
        ]
        return candidates.first { FileManager.default.isReadableFile(atPath: $0.path) }
    }

    private func pythonPathEntries(for root: URL) -> [String] {
        if FileManager.default.fileExists(atPath: root.appendingPathComponent("apps/backend/src/kenn/server.py").path) {
            return [
                root.path,
                root.appendingPathComponent("apps/backend/src").path,
                root.appendingPathComponent("packages/chat").path,
                root.appendingPathComponent("packages/mix-review/core").path
            ]
        }
        return [root.path, root.appendingPathComponent("runtime/legacy").path]
    }

    /// The self-contained beta app: Resources/python (bundled CPython) and
    /// Resources/kenn (KENN in its repository layout), built by build_kenn_app.py.
    private var bundledKENN: (python: URL, root: URL)? {
        guard let resources = Bundle.main.resourceURL else { return nil }
        let python = resources.appendingPathComponent("python/bin/python3")
        let root = resources.appendingPathComponent("kenn")
        let entry = root.appendingPathComponent("apps/backend/src/kenn/app_entry.py")
        guard FileManager.default.isExecutableFile(atPath: python.path),
              FileManager.default.isReadableFile(atPath: entry.path) else { return nil }
        return (python, root)
    }

    private func launchBundledServer(python: URL, root: URL) {
        // The bundle is read-only: KENN writes under Application Support (see app_entry.py).
        let dataFolder = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Application Support/KENN", isDirectory: true)
        try? FileManager.default.createDirectory(at: dataFolder, withIntermediateDirectories: true)
        let task = Process()
        task.executableURL = python
        task.arguments = [root.appendingPathComponent("apps/backend/src/kenn/app_entry.py").path]
        task.currentDirectoryURL = dataFolder
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = [
            root.appendingPathComponent("apps/backend/src").path,
            root.appendingPathComponent("packages/chat").path
        ].joined(separator: ":")
        environment["PYTHONNOUSERSITE"] = "1"
        environment.removeValue(forKey: "PYTHONHOME")
        task.environment = environment
        attachLog(named: "server.log", to: task)
        task.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { self?.serverProcess = nil }
        }
        do {
            try task.run()
            serverProcess = task
            setStatus("Starting KENN...", image: "arrow.clockwise.circle")
            waitForServer(remainingAttempts: 60)
        } catch {
            setStatus("Could not start KENN: \(error.localizedDescription)", image: "exclamationmark.triangle.fill")
        }
    }

    @objc private func startOrConnect() {
        if bundledKENN == nil {
            ensureAutomixWorker()  // AutoMix is a developer-checkout feature, not part of the beta app
        }
        health { [weak self] available in
            guard let self else { return }
            if available {
                self.loadKENN()
                self.setStatus("Connected to local KENN", image: "checkmark.circle.fill")
            } else {
                self.launchServer()
            }
        }
    }

    private func launchServer() {
        guard serverProcess == nil || serverProcess?.isRunning == false else { return }
        if let bundled = bundledKENN {
            launchBundledServer(python: bundled.python, root: bundled.root)
            return
        }
        guard let root = repositoryRoot, let script = serverScript(in: root) else {
            setStatus("Choose a KENN repository to start the local companion", image: "exclamationmark.triangle.fill")
            return
        }
        let python = pythonExecutable(in: root)
        let task = Process()
        task.executableURL = URL(fileURLWithPath: python)
        task.arguments = [script.path]
        task.currentDirectoryURL = root
        var environment = ProcessInfo.processInfo.environment
        let existingPythonPath = environment["PYTHONPATH"] ?? ""
        let paths = pythonPathEntries(for: root)
        environment["PYTHONPATH"] = paths.joined(separator: ":") + (existingPythonPath.isEmpty ? "" : ":" + existingPythonPath)
        task.environment = environment
        attachLog(named: "server.log", to: task)
        task.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { self?.serverProcess = nil }
        }
        do {
            try task.run()
            serverProcess = task
            setStatus("Starting local KENN...", image: "arrow.clockwise.circle")
            waitForServer(remainingAttempts: 20)
        } catch {
            setStatus("Could not start KENN: \(error.localizedDescription)", image: "exclamationmark.triangle.fill")
        }
    }

    private func ensureAutomixWorker() {
        guard automixWorkerProcess == nil || automixWorkerProcess?.isRunning == false else { return }
        guard let root = repositoryRoot else { return }
        let task = Process()
        task.executableURL = URL(fileURLWithPath: pythonExecutable(in: root))
        task.arguments = [root.appendingPathComponent("apps/backend/src/kenn/main.py").path, "worker", "kenn-desktop"]
        task.currentDirectoryURL = root
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = [root.path, root.appendingPathComponent("apps/backend/src").path].joined(separator: ":")
        task.environment = environment
        attachLog(named: "automix-worker.log", to: task)
        task.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { self?.automixWorkerProcess = nil }
        }
        do {
            try task.run()
            automixWorkerProcess = task
        } catch {
            setStatus("Could not start AutoMix worker: \(error.localizedDescription)", image: "exclamationmark.triangle.fill")
        }
    }

    private func pythonExecutable(in root: URL) -> String {
        let venvPython = root.appendingPathComponent(".venv/bin/python")
        if FileManager.default.isExecutableFile(atPath: venvPython.path) { return venvPython.path }
        for candidate in ["/usr/local/bin/python3", "/opt/homebrew/bin/python3", "/usr/bin/python3"] {
            if FileManager.default.isExecutableFile(atPath: candidate) { return candidate }
        }
        return "/usr/bin/python3"
    }

    private func attachLog(named name: String, to task: Process) {
        let directory = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/KENN Desktop Companion", isDirectory: true)
        try? FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let logURL = directory.appendingPathComponent(name)
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        if let log = try? FileHandle(forWritingTo: logURL) {
            let _ = try? log.seekToEnd()
            task.standardOutput = log
            task.standardError = log
        }
    }

    private func waitForServer(remainingAttempts: Int) {
        health { [weak self] available in
            guard let self else { return }
            if available {
                self.loadKENN()
                self.setStatus("Local KENN is ready", image: "checkmark.circle.fill")
            } else if remainingAttempts > 0 {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self.waitForServer(remainingAttempts: remainingAttempts - 1) }
            } else {
                self.setStatus("KENN did not become ready. Check its local setup.", image: "exclamationmark.triangle.fill")
            }
        }
    }

    @objc private func reloadKENN() { webView.reload() }

    @objc private func openInBrowser() { NSWorkspace.shared.open(kennURL) }

    // Setup checks plus "Save diagnostics for support", even when everything is already set up.
    @objc private func openSupport() {
        var components = URLComponents(url: kennURL.appendingPathComponent("setup"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "support", value: nil)]
        webView.load(URLRequest(url: components.url!))
    }

    private func refreshHealth() {
        health { [weak self] available in
            guard let self else { return }
            if available {
                self.setStatus("Connected to local KENN", image: "checkmark.circle.fill")
            } else if self.serverProcess == nil || self.serverProcess?.isRunning == false {
                self.setStatus("KENN is offline", image: "xmark.circle.fill")
            }
        }
    }

    private func loadKENN() {
        // The beta app opens on the setup checks; that page goes straight on to KENN when all pass.
        let url = bundledKENN != nil ? kennURL.appendingPathComponent("setup") : kennURL
        webView.load(URLRequest(url: url))
    }

    private func health(completion: @escaping (Bool) -> Void) {
        var request = URLRequest(url: kennURL.appendingPathComponent("api/health"))
        request.timeoutInterval = 1.0
        URLSession.shared.dataTask(with: request) { _, response, _ in
            let available = (response as? HTTPURLResponse)?.statusCode == 200
            DispatchQueue.main.async { completion(available) }
        }.resume()
    }

    private func setStatus(_ label: String, image: String) {
        statusItem?.label = label
        statusItem?.image = NSImage(systemSymbolName: image, accessibilityDescription: label)
    }

    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        let flac = UTType(filenameExtension: "flac")
        // WKWebView passes the HTML accept list here, but Finder can identify
        // perfectly valid WAV exports with vendor-specific UTIs.  Keep the
        // useful audio filter while allowing a user to select those files;
        // KENN's upload endpoints still validate the extension and content.
        panel.allowedContentTypes = [.audio, .wav, .aiff, .mpeg4Audio, .mp3] + (flac.map { [$0] } ?? [])
        panel.allowsOtherFileTypes = true
        panel.beginSheetModal(for: window) { result in
            completionHandler(result == .OK ? panel.urls : nil)
        }
    }
}

extension KENNDesktopCompanion: NSToolbarDelegate {
    func toolbarAllowedItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [.flexibleSpace, .space, .init("reloadKENN"), .init("start"), .init("browser"), .init("status"), .init("support")]
    }

    func toolbarDefaultItemIdentifiers(_ toolbar: NSToolbar) -> [NSToolbarItem.Identifier] {
        [.init("start"), .init("reloadKENN"), .flexibleSpace, .init("status"), .init("support"), .init("browser")]
    }

    func toolbar(_ toolbar: NSToolbar, itemForItemIdentifier identifier: NSToolbarItem.Identifier, willBeInsertedIntoToolbar flag: Bool) -> NSToolbarItem? {
        let item = NSToolbarItem(itemIdentifier: identifier)
        switch identifier.rawValue {
        case "start":
            item.label = "Start KENN"
            item.image = NSImage(systemSymbolName: "play.circle", accessibilityDescription: item.label)
            item.target = self
            item.action = #selector(startOrConnect)
        case "reloadKENN":
            item.label = "Reload"
            item.image = NSImage(systemSymbolName: "arrow.clockwise", accessibilityDescription: item.label)
            item.target = self
            item.action = #selector(reloadKENN)
        case "browser":
            item.label = "Open in Browser"
            item.image = NSImage(systemSymbolName: "safari", accessibilityDescription: item.label)
            item.target = self
            item.action = #selector(openInBrowser)
        case "support":
            item.label = "Setup & Support"
            item.image = NSImage(systemSymbolName: "lifepreserver", accessibilityDescription: item.label)
            item.target = self
            item.action = #selector(openSupport)
        case "status":
            item.label = "Connecting..."
            item.image = NSImage(systemSymbolName: "circle.dotted", accessibilityDescription: item.label)
            statusItem = item
        default:
            return nil
        }
        return item
    }
}

let application = NSApplication.shared
let companion = KENNDesktopCompanion()
application.delegate = companion
application.setActivationPolicy(.regular)
application.run()
