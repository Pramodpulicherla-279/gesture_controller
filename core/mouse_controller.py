import ctypes

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800


class MouseController:
    """Maps hand tracking to real, system-wide mouse control.

    - Index fingertip position -> OS cursor position (smoothed)
    - Thumb+index pinch (held)  -> left button down/up (click or drag)
    - Thumb+middle pinch (tap)  -> right click
    - Thumb+ring pinch (held)   -> scroll, driven by vertical hand movement
    """

    def __init__(self, smoothing=0.5, scroll_sensitivity=8):
        self.screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        self.screen_h = ctypes.windll.user32.GetSystemMetrics(1)
        self.smoothing = smoothing
        self.scroll_sensitivity = scroll_sensitivity

        self._smoothed_x = None
        self._smoothed_y = None

        self._left_down = False
        self._right_click_prev = False
        self._scroll_anchor_y = None

    def update(self, norm_x, norm_y, left_pinch, right_pinch, scroll_pinch, active):
        """Call once per frame. norm_x/norm_y are mirrored 0-1 fingertip coords.

        `active` gates whether system mouse control is engaged at all -- it's
        suppressed while our own dock/panel UI is showing so the same pinch
        doesn't both select a dock item and fire a real OS click.
        """
        if not active or norm_x is None or norm_y is None:
            self.release_all()
            return None

        pos = self._move_cursor(norm_x, norm_y)
        self._set_left_button(left_pinch)

        if right_pinch and not self._right_click_prev and not left_pinch:
            self._right_click()
        self._right_click_prev = right_pinch

        self._update_scroll(scroll_pinch and not left_pinch and not right_pinch, norm_y)

        return pos

    def release_all(self):
        """Release any held buttons and reset tracking -- call when the hand leaves the frame."""
        self._set_left_button(False)
        self._right_click_prev = False
        self._scroll_anchor_y = None
        self._smoothed_x = None
        self._smoothed_y = None

    def _move_cursor(self, norm_x, norm_y):
        target_x = norm_x * self.screen_w
        target_y = norm_y * self.screen_h

        if self._smoothed_x is None:
            self._smoothed_x, self._smoothed_y = target_x, target_y
        else:
            self._smoothed_x += (target_x - self._smoothed_x) * self.smoothing
            self._smoothed_y += (target_y - self._smoothed_y) * self.smoothing

        x, y = int(self._smoothed_x), int(self._smoothed_y)
        try:
            ctypes.windll.user32.SetCursorPos(x, y)
        except Exception as e:
            print(f"Couldn't move cursor: {e}")
        return x, y

    def _set_left_button(self, pressed):
        try:
            if pressed and not self._left_down:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                self._left_down = True
            elif not pressed and self._left_down:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                self._left_down = False
        except Exception as e:
            print(f"Couldn't set left button state: {e}")

    def _right_click(self):
        try:
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            ctypes.windll.user32.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
        except Exception as e:
            print(f"Couldn't right-click: {e}")

    def _update_scroll(self, scrolling, norm_y):
        if not scrolling:
            self._scroll_anchor_y = None
            return

        if self._scroll_anchor_y is None:
            self._scroll_anchor_y = norm_y
            return

        delta = (self._scroll_anchor_y - norm_y) * self.screen_h
        if abs(delta) > 4:
            try:
                ctypes.windll.user32.mouse_event(MOUSEEVENTF_WHEEL, 0, 0, int(delta * self.scroll_sensitivity), 0)
            except Exception as e:
                print(f"Couldn't scroll: {e}")
            self._scroll_anchor_y = norm_y
