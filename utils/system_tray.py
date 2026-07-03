import os
import pystray
from PIL import Image
import threading

def create_system_tray():
    def on_quit(icon):
        icon.stop()
        # icon.stop() only tears down the tray thread; the camera loop on the
        # main thread would otherwise keep running, so force the whole app to exit.
        os._exit(0)

    image = Image.open("assets/icons/app_icon.png")
    menu = pystray.Menu(
        pystray.MenuItem('Show', lambda: print("Show window")),
        pystray.MenuItem('Hide', lambda: print("Hide window")),
        pystray.MenuItem('Exit', on_quit)
    )
    icon = pystray.Icon("Gesture Control", image, menu=menu)
    icon.run()