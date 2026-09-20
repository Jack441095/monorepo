import AppKit
import NiteSubmitCore

// NITE Submit — macOS AppKit front end. Fully local for all document
// processing; the only network request in the app is the user-initiated
// "Check for Updates…" menu item, which fetches UpdateEngine.defaultAppcastURL.
final class AppDelegate: NSObject, NSApplicationDelegate {
    var window: NSWindow?
    var controller: SubmitController?
    private var pendingOpenURLs: [URL] = []

    private func normalizedPDFURL(_ path: String) -> URL? {
        let candidate = URL(fileURLWithPath: path)
        let url = candidate.path.hasPrefix("/")
            ? candidate
            : URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
                .appendingPathComponent(path)
        guard url.pathExtension.lowercased() == "pdf",
              FileManager.default.fileExists(atPath: url.path) else { return nil }
        return url.standardizedFileURL
    }

    private func openPDF(_ url: URL) {
        guard url.pathExtension.lowercased() == "pdf" else { return }
        // Route through the same path drag-and-drop uses (MainView.handleFilesDropped) rather
        // than calling the controller directly. Calling the controller alone left the visible
        // queue rack and review fields showing stale/placeholder content while the real file was
        // silently loaded underneath — the screen would show fake "verified" data for a different
        // file than the one actually being approved.
        guard let controller, let view = controller.view else {
            pendingOpenURLs.append(url)
            return
        }
        view.handleFilesDropped([url])
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let win = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 620, height: 720),
                           styleMask: [.titled, .closable, .miniaturizable, .resizable],
                           backing: .buffered, defer: false)
        win.minSize = NSSize(width: 540, height: 520)
        win.maxSize = NSSize(width: 900, height: 1200)
        win.title = "Submit"
        win.appearance = NSAppearance(named: .aqua)
        win.center()
        win.orderFrontRegardless()
        window = win
        NSApp.activate(ignoringOtherApps: true)
        NSRunningApplication.current.activate(options: [.activateAllWindows,
                                                         .activateIgnoringOtherApps])
        setupMainMenu()

        if LicenseEngine.isLicensed() {
            showMainUI()
        } else {
            let licenseView = LicenseView(frame: win.contentView!.bounds)
            licenseView.onActivated = { [weak self] in self?.showMainUI() }
            win.contentView = licenseView
            win.makeKeyAndOrderFront(nil)
        }
    }

    private func showMainUI() {
        guard let win = window else { return }
        let content = MainView(frame: NSRect(x: 0, y: 0, width: 620, height: 720))
        let c = SubmitController(view: content)
        content.controller = c
        controller = c
        win.contentView = content
        win.makeKeyAndOrderFront(nil)
        content.promptForDefaultStudentIdIfNeeded()

        let queued = pendingOpenURLs
        pendingOpenURLs.removeAll()
        for url in queued {
            openPDF(url)
            break
        }
    }

    private var updateModalController: UpdateModalView?
    private weak var checkForUpdatesItem: NSMenuItem?

    private static var currentVersionString: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0"
    }

    private func setupMainMenu() {
        let mainMenu = NSMenu()

        // App Menu
        let appMenuItem = NSMenuItem()
        let appMenu = NSMenu(title: "NITE Submit")
        let checkForUpdatesItem = NSMenuItem(title: "Check for Updates…", action: #selector(checkForUpdates), keyEquivalent: "u")
        checkForUpdatesItem.keyEquivalentModifierMask = [.command, .shift]
        appMenu.addItem(checkForUpdatesItem)
        appMenu.addItem(NSMenuItem.separator())
        let manageLicenceItem = NSMenuItem(title: "Manage Licence…", action: #selector(showLicenceEntry), keyEquivalent: "l")
        manageLicenceItem.keyEquivalentModifierMask = [.command, .shift]
        appMenu.addItem(manageLicenceItem)
        appMenu.addItem(NSMenuItem.separator())
        appMenu.addItem(withTitle: "Quit NITE Submit", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appMenuItem.submenu = appMenu
        mainMenu.addItem(appMenuItem)

        self.checkForUpdatesItem = checkForUpdatesItem
        NSApp.mainMenu = mainMenu
    }

    @objc func showLicenceEntry() {
        guard let win = window else { return }
        let licenseView = LicenseView(frame: win.contentView!.bounds)
        licenseView.onActivated = { [weak self] in self?.showMainUI() }
        win.contentView = licenseView
    }

    @objc func checkForUpdates() {
        let currentVersionStr = Self.currentVersionString
        checkForUpdatesItem?.isEnabled = false
        checkForUpdatesItem?.title = "Checking for Updates…"

        let feedURL = UpdateEngine.defaultAppcastURL
        let task = URLSession.shared.dataTask(with: feedURL) { [weak self] data, response, error in
            DispatchQueue.main.async {
                self?.checkForUpdatesItem?.isEnabled = true
                self?.checkForUpdatesItem?.title = "Check for Updates…"

                guard let data, error == nil else {
                    let errAlert = NSAlert()
                    errAlert.messageText = "Update Check Failed"
                    errAlert.informativeText = error?.localizedDescription ?? "Could not reach nitedsp.co.uk. Check your internet connection and try again."
                    errAlert.runModal()
                    return
                }

                let engine = UpdateEngine()
                let result = engine.checkStatus(feedData: data, currentVersionString: currentVersionStr)
                switch result {
                case .updateAvailable(let item, let currentVer, _):
                    let modal = UpdateModalView(item: item, currentVersion: currentVer)
                    self?.updateModalController = modal
                    modal.showWindow(nil)
                    modal.window?.makeKeyAndOrderFront(nil)
                    NSApp.activate(ignoringOtherApps: true)
                case .upToDate:
                    let okAlert = NSAlert()
                    okAlert.messageText = "NITE Submit is Up to Date"
                    okAlert.informativeText = "NITE Submit \(currentVersionStr) is currently the latest version available."
                    okAlert.runModal()
                case .failed(let reason):
                    let errAlert = NSAlert()
                    errAlert.messageText = "Update Check Failed"
                    errAlert.informativeText = reason
                    errAlert.runModal()
                }
            }
        }
        task.resume()
    }

    func application(_ sender: NSApplication, openFile filename: String) -> Bool {
        if let url = normalizedPDFURL(filename) { openPDF(url) }
        return true
    }

    func application(_ sender: NSApplication, openFiles filenames: [String]) {
        for filename in filenames {
            guard let url = normalizedPDFURL(filename) else { continue }
            openPDF(url)
            break
        }
        sender.reply(toOpenOrPrint: .success)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
// NSApplication's delegate reference is weak. Keep the delegate alive for
// the entire event loop; without this explicit lifetime the optimised release
// binary can deallocate it before applicationDidFinishLaunching, leaving a
// headless process with no window.
withExtendedLifetime(delegate) {
    app.run()
}
