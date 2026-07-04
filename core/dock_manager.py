import time
import cv2

from core import ui_theme
from utils.helpers import open_windows_panel

TABS = ('volume', 'apps', 'wifi', 'bluetooth')
TAB_LABELS = {'volume': 'Volume', 'apps': 'Apps', 'wifi': 'WiFi', 'bluetooth': 'Bluetooth'}
TAB_GLYPHS = {'volume': 'VOL', 'apps': 'APP', 'wifi': 'WiFi', 'bluetooth': 'BT'}

CLOSE_DELAY = 3.0  # seconds the dock stays up after the palm closes, before hiding
PINCH_SELECT_COOLDOWN = 0.4

DOCK_ICON_RADIUS = 34
DOCK_ICON_GAP = 26
DOCK_BOTTOM_MARGIN = 60

PANEL_WIDTH = 520
PANEL_HEIGHT = 220
PANEL_BOTTOM_GAP = 30  # gap between panel bottom and dock top


class DockManager:
    """
    VisionOS-style interaction model:
      - hand goes from closed to open (edge, not "is currently open" every
        frame) -> the floating dock (Volume/Apps/WiFi/Bluetooth) appears,
        showing whichever panel is currently active, above the dock
      - hand goes from open to closed (edge) -> a 3s grace-period countdown
        starts; opening the palm again before it elapses cancels the hide,
        otherwise the dock hides. Using the transition rather than the
        continuous "palm is open" state means a sustained (but incorrectly
        classified) open-looking hand shape during mouse-mode gestures only
        opens the dock once, instead of re-triggering it every single frame.
      - hover a dock icon (fingertip over it) = highlight (visionOS 'gaze',
        simulated with the fingertip since there's no eye tracking)
      - pinch while hovered = select (visionOS 'pinch') -> switches panels
      - each panel handles its own pinch-driven interaction
    """

    def __init__(self, display_width, display_height, volume_controller, window_controller):
        self.display_width = display_width
        self.display_height = display_height
        self.volume_controller = volume_controller
        self.window_controller = window_controller

        self.active_panel = 'volume'
        self.components_visible = False
        self.closing_timer_start = None
        self._prev_palm_open = False

        self._prev_pinching = False
        self.pinch_started = False
        self.last_select_time = 0

        self.volume_dragging = False
        self.volume_level = self.volume_controller.get_volume()

        self.window_previews = []
        self.last_window_refresh = 0
        self.window_refresh_cooldown = 2.0

    # ------------------------------------------------------------------ #
    # Per-frame update
    # ------------------------------------------------------------------ #
    def update(self, index_tip, thumb_tip, pinching, palm_open):
        pinch_started = pinching and not self._prev_pinching
        self._prev_pinching = pinching
        self.pinch_started = pinch_started

        current_time = time.time()

        # Edge-triggered, not level-triggered: only the closed->open and
        # open->closed transitions act. Reacting to "palm_open is currently
        # True" every frame meant a sustained (even if wrongly-classified)
        # open-looking hand during mouse-mode gestures kept re-showing the
        # dock and cancelling the close countdown on every single frame.
        opened_edge = palm_open and not self._prev_palm_open
        closed_edge = (not palm_open) and self._prev_palm_open
        self._prev_palm_open = palm_open

        if opened_edge:
            self.components_visible = True
            self.closing_timer_start = None
        elif closed_edge and self.components_visible:
            self.closing_timer_start = current_time

        if self.components_visible and self.closing_timer_start is not None:
            if current_time - self.closing_timer_start >= CLOSE_DELAY:
                self.components_visible = False
                self.closing_timer_start = None

        if not self.components_visible:
            self.volume_dragging = False
            return

        self._update_dock(index_tip, pinch_started)

        if self.active_panel == 'volume':
            self._update_volume(index_tip, pinching)
        elif self.active_panel == 'apps':
            self._update_apps(index_tip, pinch_started)
        elif self.active_panel in ('wifi', 'bluetooth'):
            self._update_settings_shortcut(index_tip, pinch_started)

    def _update_dock(self, index_tip, pinch_started):
        if index_tip is None or not pinch_started:
            return
        for tab, center in self._dock_icon_positions():
            if self._point_in_circle(index_tip, center, DOCK_ICON_RADIUS):
                now = time.time()
                if now - self.last_select_time >= PINCH_SELECT_COOLDOWN:
                    self.last_select_time = now
                    self.active_panel = tab
                break

    def _update_volume(self, index_tip, pinching):
        bar_x, bar_y, bar_w, bar_h = self._volume_bar_rect()
        knob_x = bar_x + int((self.volume_level / 100) * bar_w)
        knob_y = bar_y + bar_h // 2

        if index_tip is None:
            self.volume_dragging = False
            return

        near_knob = abs(index_tip[0] - knob_x) < 26 and abs(index_tip[1] - knob_y) < 26
        near_track = abs(index_tip[1] - knob_y) < 26

        if pinching and (near_knob or self.volume_dragging):
            self.volume_dragging = True
        elif not pinching or not near_track:
            self.volume_dragging = False

        if self.volume_dragging:
            vol = int(((index_tip[0] - bar_x) / bar_w) * 100)
            vol = max(0, min(100, vol))
            if vol != self.volume_level:
                self.volume_controller.set_volume(vol)
                self.volume_level = vol

    def _update_apps(self, index_tip, pinch_started):
        now = time.time()
        if now - self.last_window_refresh > self.window_refresh_cooldown:
            self.window_previews = self.window_controller.get_windows()
            self.last_window_refresh = now

        if index_tip is None or not pinch_started:
            return

        for i, rect in enumerate(self._app_thumbnail_rects()):
            if self._point_in_rect(index_tip, rect):
                self.window_controller.activate_window(i)
                break

    def _update_settings_shortcut(self, index_tip, pinch_started):
        if index_tip is None or not pinch_started:
            return
        if self._point_in_rect(index_tip, self._settings_button_rect()):
            section = 'network-wifi' if self.active_panel == 'wifi' else 'bluetooth'
            open_windows_panel(section)

    # ------------------------------------------------------------------ #
    # Drawing
    # ------------------------------------------------------------------ #
    def draw(self, frame, index_tip):
        if not self.components_visible:
            return
        self._draw_panel(frame, index_tip)
        self._draw_dock(frame, index_tip)

    def draw_countdown(self, frame, palm_center):
        if self.closing_timer_start is None:
            return
        remaining = max(0.0, CLOSE_DELAY - (time.time() - self.closing_timer_start))
        center = palm_center or (self.display_width // 2, self.display_height // 2)
        ui_theme.draw_countdown_ring(frame, center, remaining, CLOSE_DELAY)

    def _draw_dock(self, frame, index_tip):
        for tab, center in self._dock_icon_positions():
            hovered = index_tip is not None and self._point_in_circle(index_tip, center, DOCK_ICON_RADIUS)
            selected = tab == self.active_panel
            ui_theme.draw_dock_icon(frame, center, DOCK_ICON_RADIUS, TAB_GLYPHS[tab],
                                     hovered=hovered, selected=selected)

    def _draw_panel(self, frame, index_tip):
        x, y, w, h = self._panel_rect()
        ui_theme.frosted_panel(frame, x, y, w, h, radius=28, tint_alpha=0.3)

        title = TAB_LABELS.get(self.active_panel, '')
        cv2.putText(frame, title, (x + 20, y + 32), cv2.FONT_HERSHEY_SIMPLEX, 0.6, ui_theme.WHITE, 1, cv2.LINE_AA)

        if self.active_panel == 'volume':
            self._draw_volume(frame)
        elif self.active_panel == 'apps':
            self._draw_apps(frame, index_tip)
        elif self.active_panel in ('wifi', 'bluetooth'):
            self._draw_settings_shortcut(frame, index_tip)

    def _draw_volume(self, frame):
        bar_x, bar_y, bar_w, bar_h = self._volume_bar_rect()
        fraction = self.volume_level / 100

        ui_theme.frosted_panel(frame, bar_x, bar_y, bar_w, bar_h, radius=bar_h // 2,
                               tint_alpha=0.25, border_thickness=1)
        filled_w = int(bar_w * fraction)
        if filled_w > 6:
            overlay = frame.copy()
            cv2.rectangle(overlay, (bar_x, bar_y), (bar_x + filled_w, bar_y + bar_h), ui_theme.GLOW, -1)
            cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, dst=frame)

        knob_x, knob_y = bar_x + filled_w, bar_y + bar_h // 2
        color = ui_theme.ACCENT if self.volume_dragging else ui_theme.GLOW
        cv2.circle(frame, (knob_x, knob_y), bar_h // 2 + 8, color, -1, lineType=cv2.LINE_AA)
        cv2.circle(frame, (knob_x, knob_y), bar_h // 2 + 8, ui_theme.WHITE, 1, lineType=cv2.LINE_AA)

        cv2.putText(frame, f"{self.volume_level}%", (bar_x + bar_w + 15, bar_y + bar_h),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.55, ui_theme.WHITE, 1, cv2.LINE_AA)
        cv2.putText(frame, "Pinch the knob and drag to change volume", (bar_x, bar_y + bar_h + 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, ui_theme.DIM_TEXT, 1, cv2.LINE_AA)

    def _draw_apps(self, frame, index_tip):
        for win, rect in zip(self.window_previews, self._app_thumbnail_rects()):
            x, y, w, h = rect
            hovered = index_tip is not None and self._point_in_rect(index_tip, rect)
            icon = self.window_controller.get_icon(win._hWnd, 28)
            title = win.title[:14] + "..." if len(win.title) > 14 else win.title

            ui_theme.draw_glass_button(frame, x, y, w, h, "", hovered=hovered)
            ui_theme.blit_bgra(frame, icon, (x + (w - 28) // 2, y + 8))

            text_size = cv2.getTextSize(title, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)[0]
            cv2.putText(frame, title, (x + max(2, (w - text_size[0]) // 2), y + h - 8),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.38, ui_theme.WHITE, 1, cv2.LINE_AA)

        if not self.window_previews:
            px, py, pw, ph = self._panel_rect()
            cv2.putText(frame, "No windows found", (px + 20, py + 70),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, ui_theme.DIM_TEXT, 1, cv2.LINE_AA)

    def _draw_settings_shortcut(self, frame, index_tip):
        rect = self._settings_button_rect()
        hovered = index_tip is not None and self._point_in_rect(index_tip, rect)
        label = "Open WiFi Settings" if self.active_panel == 'wifi' else "Open Bluetooth Settings"
        ui_theme.draw_glass_button(frame, *rect, label, hovered=hovered)

        px, py, pw, ph = self._panel_rect()
        cv2.putText(frame, "Pinch the button to open Windows Settings", (px + 20, py + 130),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, ui_theme.DIM_TEXT, 1, cv2.LINE_AA)

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #
    def _dock_icon_positions(self):
        total_w = len(TABS) * (DOCK_ICON_RADIUS * 2) + (len(TABS) - 1) * DOCK_ICON_GAP
        start_x = (self.display_width - total_w) // 2 + DOCK_ICON_RADIUS
        y = self.display_height - DOCK_BOTTOM_MARGIN
        positions = []
        for i, tab in enumerate(TABS):
            cx = start_x + i * (DOCK_ICON_RADIUS * 2 + DOCK_ICON_GAP)
            positions.append((tab, (cx, y)))
        return positions

    def _panel_rect(self):
        x = (self.display_width - PANEL_WIDTH) // 2
        dock_top = self.display_height - DOCK_BOTTOM_MARGIN - DOCK_ICON_RADIUS
        y = dock_top - PANEL_BOTTOM_GAP - PANEL_HEIGHT
        return (x, y, PANEL_WIDTH, PANEL_HEIGHT)

    def _volume_bar_rect(self):
        x, y, w, h = self._panel_rect()
        return (x + 20, y + 70, w - 200, 24)

    def _app_thumbnail_rects(self):
        x, y, w, h = self._panel_rect()
        cols = 4
        tw, th = 100, 90
        gap = 14
        rects = []
        for i in range(len(self.window_previews)):
            row, col = divmod(i, cols)
            rx = x + 20 + col * (tw + gap)
            ry = y + 45 + row * (th + gap)
            rects.append((rx, ry, tw, th))
        return rects

    def _settings_button_rect(self):
        x, y, w, h = self._panel_rect()
        return (x + 20, y + 60, 260, 50)

    @staticmethod
    def _point_in_rect(point, rect):
        px, py = point
        x, y, w, h = rect
        return x <= px <= x + w and y <= py <= y + h

    @staticmethod
    def _point_in_circle(point, center, radius):
        dx = point[0] - center[0]
        dy = point[1] - center[1]
        return (dx * dx + dy * dy) ** 0.5 <= radius
