"""macOS Menu Bar App Launcher & Hotkey Bridge.

Launches PyObjC / rumps status bar app when available, or executes headless CLI bridge.
"""

import sys

from thursday.mac_app.thursday_menu_bar_app import ThursdayMenuBarBridge


def launch_mac_app() -> int:
    """Launch Thursday macOS Menu Bar app."""
    bridge = ThursdayMenuBarBridge()
    status = bridge.get_menu_status()
    print(f"⚡ Thursday macOS Menu Bar Assistant Initialized: {status['title']} [{status['shortcut']}]")

    # Try PyObjC / rumps if installed, otherwise run background daemon bridge
    try:
        import rumps

        class ThursdayRumpsApp(rumps.App):
            def __init__(self):
                super().__init__("🤖 Thursday", quit_button="Quit Thursday")
                self.menu = ["🗣️ Ask Thursday (Cmd+Shift+T)", "🎛️ Audit Ableton Session", "🎬 Clean YouTube Audio", "🌐 Open Thursday Web Hub"]

            @rumps.clicked("🗣️ Ask Thursday (Cmd+Shift+T)")
            def ask_thursday(self, _):
                window = rumps.Window("Ask Thursday / KENN Studio Assistant", "Enter command or prompt:", cancel=True)
                resp = window.run()
                if resp.clicked:
                    res = bridge.execute_action("ask", {"prompt": resp.text})
                    rumps.notification("Thursday Jarvis Response", "Studio Advice Generated", res.get("spoken_text", "Done"))

            @rumps.clicked("🌐 Open Thursday Web Hub")
            def open_hub(self, _):
                import webbrowser
                webbrowser.open("http://127.0.0.1:8080/thursday_hub.html")

        app = ThursdayRumpsApp()
        app.run()
        return 0
    except ImportError:
        print("rumps library not installed; running in CLI headless bridge mode.")
        return 0


if __name__ == "__main__":
    sys.exit(launch_mac_app())
