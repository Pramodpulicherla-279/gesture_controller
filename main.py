import cv2
import argparse
import threading
import numpy as np
import time
import ctypes
import win32gui
import win32con
from core.gesture_controller import GestureController
from core.volume_controller import VolumeController
from core.window_controller import WindowController
from core.dock_manager import DockManager
from core.mouse_controller import MouseController
from core import ui_theme
from utils.system_tray import create_system_tray
from utils.helpers import load_config

# Constants for display dimensions
DISPLAY_WIDTH = 840
DISPLAY_HEIGHT = 680


def set_window_transparency(hwnd, opacity):
    """Make the overlay click-through and glass-like.

    WS_EX_TRANSPARENT lets mouse clicks/scrolls pass straight through to
    whatever is underneath, so the fullscreen overlay doesn't block you from
    working in other windows/tabs. LWA_COLORKEY makes pure black fully
    transparent -- only what the dock/panels actually draw shows up, at
    `opacity`, instead of a flat dim wash over the whole screen.
    """
    try:
        WS_EX_LAYERED = 0x80000
        WS_EX_TRANSPARENT = 0x20
        LWA_COLORKEY = 0x1
        LWA_ALPHA = 0x2
        ex_style = ctypes.windll.user32.GetWindowLongA(hwnd, -20)
        ctypes.windll.user32.SetWindowLongA(hwnd, -20, ex_style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
        ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0x000000, opacity, LWA_COLORKEY | LWA_ALPHA)
    except Exception as e:
        print(f"Couldn't set transparency: {e}")


def set_topmost(hwnd, topmost):
    """Toggle whether the overlay stays above every other window.

    A WS_EX_TOPMOST window keeps rendering above whatever you click into,
    even though clicks pass through it (WS_EX_TRANSPARENT) -- in mouse mode
    that meant the app you just clicked into could never actually become the
    true foreground/top window, breaking activation and anything that
    depends on real window focus. So: topmost only while the dock is
    showing (it needs to render above everything); dropped to normal
    z-order the rest of the time, when the real OS cursor (drawn by Windows
    itself, unaffected by our own z-order) is the only visual feedback
    needed anyway.
    """
    try:
        flag = win32con.HWND_TOPMOST if topmost else win32con.HWND_NOTOPMOST
        win32gui.SetWindowPos(hwnd, flag, 0, 0, 0, 0, win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
    except Exception as e:
        print(f"Couldn't set topmost state: {e}")


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Gesture Control System')
    parser.add_argument('--calibrate', action='store_true',
                       help='Enter calibration mode')
    args = parser.parse_args()

    # Load configuration
    config = load_config('config/default_config.yaml')

    if args.calibrate:
        from utils.helpers import calibration_mode
        calibration_mode()
        return

    # Initialize controllers
    gesture_controller = GestureController(config)
    volume_controller = VolumeController()
    window_controller = WindowController()
    dock_manager = DockManager(DISPLAY_WIDTH, DISPLAY_HEIGHT, volume_controller, window_controller)
    mouse_controller = MouseController()

    # Start system tray icon
    tray_thread = threading.Thread(target=create_system_tray, daemon=True)
    tray_thread.start()

    # Main processing loop
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, DISPLAY_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, DISPLAY_HEIGHT)

    # Create named window in fullscreen mode
    cv2.namedWindow('Gesture Control System', cv2.WINDOW_NORMAL)
    cv2.setWindowProperty('Gesture Control System', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    # Glass elements render at 90% opacity; pure-black areas are fully
    # transparent (see set_window_transparency), so apps underneath stay crisp.
    opacity_percent = 90
    hwnd = win32gui.FindWindow(None, 'Gesture Control System')
    set_window_transparency(hwnd, int(255 * opacity_percent / 100))

    # Topmost state is toggled dynamically in the loop based on whether the
    # dock is showing (see set_topmost). Starts non-topmost since the dock
    # starts hidden.
    is_topmost = False
    set_topmost(hwnd, is_topmost)

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Create a black background with consistent dimensions
        display_frame = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, 3), dtype=np.uint8)

        try:
            # Process the original frame (not flipped)
            results = gesture_controller.process_frame(frame)
            index_tip = None
            thumb_tip = None
            palm_center = None
            pinching = False
            palm_open = False
            right_click_pinch = False
            scroll_pinch = False
            norm_x = None
            norm_y = None

            if results and results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    pinching = gesture_controller.is_pinching(hand_landmarks)
                    palm_open = gesture_controller.is_palm_open(hand_landmarks)
                    right_click_pinch = gesture_controller.is_right_click_pinch(hand_landmarks)
                    scroll_pinch = gesture_controller.is_scroll_pinch(hand_landmarks)

                    landmarks = hand_landmarks.landmark

                    # Mirrored, resolution-independent (0-1) fingertip position,
                    # used to drive the real OS cursor regardless of camera resolution
                    norm_x = 1.0 - landmarks[8].x
                    norm_y = landmarks[8].y

                    # Get finger positions (using display dimensions)
                    # Flip the x-coordinate to match the display (mirror-like movement)
                    index_tip = (DISPLAY_WIDTH - int(landmarks[8].x * DISPLAY_WIDTH),
                                int(landmarks[8].y * DISPLAY_HEIGHT))
                    thumb_tip = (DISPLAY_WIDTH - int(landmarks[4].x * DISPLAY_WIDTH),
                                int(landmarks[4].y * DISPLAY_HEIGHT))
                    palm_center = (DISPLAY_WIDTH - int(landmarks[0].x * DISPLAY_WIDTH),
                                int(landmarks[0].y * DISPLAY_HEIGHT))

            # Drive the dock/panel state machine (palm-open show/hide, dock
            # icon hover+pinch selection, and whichever panel is active)
            dock_manager.update(index_tip, thumb_tip, pinching, palm_open)

            if dock_manager.components_visible != is_topmost:
                is_topmost = dock_manager.components_visible
                set_topmost(hwnd, is_topmost)

            dock_manager.draw(display_frame, index_tip)
            dock_manager.draw_countdown(display_frame, palm_center)

            # System-wide mouse control -- only engaged while the dock isn't
            # showing, so the same pinch doesn't both pick a dock item and
            # fire a real OS click at the same time.
            mouse_controller.update(norm_x, norm_y, pinching, right_click_pinch,
                                    scroll_pinch, active=not dock_manager.components_visible)

            # VisionOS never renders your hand as a 3D model -- tracking is
            # invisible and only the UI reacts. A small glow stands in for
            # the (nonexistent) eye-tracking gaze point.
            if index_tip:
                ui_theme.draw_focus_cursor(display_frame, index_tip, pinching=pinching)

            # Instructions
            if dock_manager.components_visible:
                instructions = [
                    "Hover a dock icon and pinch to switch panels",
                    "Pinch the volume knob to grab and drag it",
                    "Press 'q' to quit"
                ]
            else:
                instructions = [
                    "Mouse mode: point to move, thumb+index pinch to click/drag,",
                    "thumb+middle to right-click, thumb+ring (hold) to scroll",
                    "Open your palm to show the dock instead",
                    "Press 'q' to quit"
                ]

            for i, text in enumerate(instructions):
                cv2.putText(display_frame, text, (20, DISPLAY_HEIGHT - 70 + i*20),
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

            cv2.imshow('Gesture Control System', display_frame)

        except Exception as e:
            print(f"Error: {e}")
            cv2.imshow('Gesture Control System', display_frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
