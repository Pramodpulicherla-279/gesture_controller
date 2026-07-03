import pygetwindow as gw
import time
import win32gui
import win32con
import win32ui
import win32api
import win32process
import pywintypes
import ctypes
import numpy as np

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
        self._icon_cache = {}
        self._window_order = []  # persisted hwnd order, independent of Z-order
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
        """Get visible windows, keeping their list order stable across refreshes.

        Order is NOT re-derived from Z-order each time -- activating a window
        changes its Z-order, which previously reshuffled the whole preview
        list on the very next refresh. Instead, existing windows keep their
        position; only newly-opened windows get appended and closed ones
        removed.
        """
        if time.time() - self.last_refresh < self.refresh_cooldown:
            return

        try:
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
            current_by_hwnd = dict(temp_windows)

            # Keep known windows in their existing order (refreshing their
            # title in case it changed), then append any newly-seen windows.
            ordered = [(hwnd, current_by_hwnd[hwnd]) for hwnd, _ in self._window_order
                       if hwnd in current_by_hwnd]
            known_hwnds = {hwnd for hwnd, _ in ordered}
            for hwnd, title in temp_windows:
                if hwnd not in known_hwnds:
                    ordered.append((hwnd, title))
                    known_hwnds.add(hwnd)

            self._window_order = ordered

            # Convert to pygetwindow objects, preserving the order above and
            # leaving out whichever window is currently focused -- no point
            # offering to "switch to" the app you're already on. It keeps its
            # slot in self._window_order so it reappears in the same spot
            # once it's no longer the active window, instead of moving to
            # the end of the list.
            foreground_hwnd = win32gui.GetForegroundWindow()
            all_windows = gw.getAllWindows()
            self.windows = []
            for hwnd, title in ordered:
                if hwnd == foreground_hwnd:
                    continue
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

    def get_icon(self, hwnd, size=32):
        """Return the window's app icon as a (size, size, 4) BGRA numpy array, or None."""
        if hwnd in self._icon_cache:
            return self._icon_cache[hwnd]

        icon_img = None
        try:
            hicon = self._get_window_hicon(hwnd) or self._get_exe_hicon(hwnd)
            if hicon:
                icon_img = self._hicon_to_bgra(hicon, size)
                win32gui.DestroyIcon(hicon)
        except Exception as e:
            print(f"Icon extraction failed: {e}")

        self._icon_cache[hwnd] = icon_img
        return icon_img

    ICON_SMALL2 = 2  # not exposed by win32con; see WM_GETICON docs

    @staticmethod
    def _get_window_hicon(hwnd):
        """Ask the window itself for its icon (accurate for well-behaved apps)."""
        for icon_type in (win32con.ICON_BIG, WindowController.ICON_SMALL2, win32con.ICON_SMALL):
            try:
                _, hicon = win32gui.SendMessageTimeout(
                    hwnd, win32con.WM_GETICON, icon_type, 0, win32con.SMTO_ABORTIFHUNG, 100)
                if hicon:
                    return hicon
            except Exception:
                pass
        try:
            hicon = win32gui.GetClassLong(hwnd, win32con.GCL_HICON)
            if hicon:
                return hicon
        except Exception:
            pass
        return 0

    @staticmethod
    def _get_exe_hicon(hwnd):
        """Fall back to the icon embedded in the owning process's executable."""
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            hprocess = win32api.OpenProcess(
                win32con.PROCESS_QUERY_INFORMATION | win32con.PROCESS_VM_READ, False, pid)
            exe_path = win32process.GetModuleFileNameEx(hprocess, 0)
            large, small = win32gui.ExtractIconEx(exe_path, 0)
            for h in small:
                win32gui.DestroyIcon(h)
            if large:
                hicon = large[0]
                for h in large[1:]:
                    win32gui.DestroyIcon(h)
                return hicon
        except Exception:
            pass
        return 0

    @staticmethod
    def _hicon_to_bgra(hicon, size):
        """Render an HICON into an off-screen bitmap and return it as a BGRA numpy array."""
        hdc_screen = win32gui.GetDC(0)
        hdc = win32ui.CreateDCFromHandle(hdc_screen)
        hdc_mem = hdc.CreateCompatibleDC()
        hbmp = win32ui.CreateBitmap()
        hbmp.CreateCompatibleBitmap(hdc, size, size)
        hdc_mem.SelectObject(hbmp)
        hdc_mem.DrawIcon((0, 0), hicon)

        bmpinfo = hbmp.GetInfo()
        bmpstr = hbmp.GetBitmapBits(True)
        img = np.frombuffer(bmpstr, dtype=np.uint8).reshape(
            (bmpinfo['bmHeight'], bmpinfo['bmWidth'], 4)).copy()

        win32gui.DeleteObject(hbmp.GetHandle())
        hdc_mem.DeleteDC()
        hdc.DeleteDC()
        win32gui.ReleaseDC(0, hdc_screen)

        return img

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