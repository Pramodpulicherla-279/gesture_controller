import pygetwindow as gw
import time
import win32gui
import win32con
import pywintypes
import ctypes

# Constants for Windows API
SW_RESTORE = 9
SW_MAXIMIZE = 3
SW_MINIMIZE = 6

class WindowController:
    def __init__(self):
        self.windows = []
        self.last_refresh = 0
        self.refresh_cooldown = 2.0
        self.last_activation_time = 0
        self.activation_cooldown = 0.3  # seconds
        self.refresh_windows()

    def _bring_to_foreground(self, hwnd):
        """Force a window to the foreground using multiple methods"""
        try:
            # Try the Alt-tab simulation method
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)  # Alt
            ctypes.windll.user32.keybd_event(0x09, 0, 0, 0)  # Tab
            ctypes.windll.user32.keybd_event(0x09, 0, 2, 0)  # Release Tab
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)  # Release Alt
            
            # Direct foreground approach
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            
            # Additional method for stubborn windows
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.BringWindowToTop(hwnd)
            
        except Exception as e:
            print(f"Foreground error: {e}")

    def refresh_windows(self):
        """Get visible windows sorted by Z-order"""
        if time.time() - self.last_refresh < self.refresh_cooldown:
            return
            
        try:
            self.windows = []
            temp_windows = []
            
            def enum_handler(hwnd, _):
                if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                    title = win32gui.GetWindowText(hwnd)
                    if title == 'Gesture Control System':
                        # Don't let the app enumerate its own control window
                        return True
                    try:
                        rect = win32gui.GetWindowRect(hwnd)
                        if rect[2]-rect[0] > 100 and rect[3]-rect[1] > 100:  # Minimum size
                            temp_windows.append((hwnd, title))
                    except:
                        pass
                return True
                
            win32gui.EnumWindows(enum_handler, None)
            
            # Sort by Z-order
            sorted_windows = []
            hwnd = win32gui.GetTopWindow(None)
            while hwnd:
                for win in temp_windows:
                    if win[0] == hwnd:
                        sorted_windows.append(win)
                        break
                hwnd = win32gui.GetWindow(hwnd, win32con.GW_HWNDNEXT)
            
            # Convert to pygetwindow objects
            all_windows = gw.getAllWindows()
            for hwnd, title in sorted_windows:
                for win in all_windows:
                    if hasattr(win, '_hWnd') and win._hWnd == hwnd and win.title == title:
                        self.windows.append(win)
                        break
            
            self.last_refresh = time.time()
            
        except Exception as e:
            print(f"Refresh error: {e}")

    def get_windows(self):
        """Return list of available windows"""
        self.refresh_windows()
        return self.windows

    def activate_window(self, index):
        """Activate specific window by index with guaranteed foreground focus"""
        if time.time() - self.last_activation_time < self.activation_cooldown:
            return
            
        if 0 <= index < len(self.windows):
            try:
                window = self.windows[index]
                hwnd = window._hWnd
                
                # Get current window state
                placement = win32gui.GetWindowPlacement(hwnd)
                was_maximized = placement[1] == win32con.SW_SHOWMAXIMIZED
                was_minimized = placement[1] == win32con.SW_SHOWMINIMIZED
                
                # Restore if minimized
                if was_minimized:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                
                # Bring to foreground using multiple methods
                self._bring_to_foreground(hwnd)
                
                # Restore original maximized state if needed
                if was_maximized:
                    win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
                
                self.last_activation_time = time.time()
                
            except Exception as e:
                print(f"Window activation failed: {e}")
                self.refresh_windows()