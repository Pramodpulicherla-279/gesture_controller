import cv2
import numpy as np

# Colors are BGR (OpenCV convention). VisionOS-style palette: light glass on
# a dark canvas, soft blue-white glow for focus, warm accent for selection --
# deliberately not the neon-cyan sci-fi look of the earlier hologram redesign.
WHITE = (255, 255, 255)
GLASS_TINT = (255, 255, 255)
GLOW = (255, 220, 150)       # soft blue-white glow, used for hover/focus
ACCENT = (60, 180, 255)      # warm accent, used for selected state
DIM_TEXT = (210, 210, 210)
DARK_TEXT = (30, 30, 30)


def blit_bgra(frame, bgra_img, pos):
    """Alpha-blend a BGRA image onto frame at pos=(x, y)."""
    if bgra_img is None:
        return
    x, y = int(pos[0]), int(pos[1])
    h, w = bgra_img.shape[:2]
    if x < 0 or y < 0 or x + w > frame.shape[1] or y + h > frame.shape[0]:
        return

    roi = frame[y:y+h, x:x+w].astype(np.float32)
    icon_bgr = bgra_img[:, :, :3].astype(np.float32)
    alpha = (bgra_img[:, :, 3:4].astype(np.float32)) / 255.0
    frame[y:y+h, x:x+w] = (icon_bgr * alpha + roi * (1 - alpha)).astype(np.uint8)


def _rounded_rect_mask(w, h, radius):
    radius = max(1, min(radius, w // 2, h // 2))
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.rectangle(mask, (radius, 0), (w - radius, h), 255, -1)
    cv2.rectangle(mask, (0, radius), (w, h - radius), 255, -1)
    for cx, cy in ((radius, radius), (w - radius, radius), (radius, h - radius), (w - radius, h - radius)):
        cv2.circle(mask, (cx, cy), radius, 255, -1)
    return mask


def _draw_rounded_border(frame, x, y, w, h, radius, color, thickness=1):
    radius = max(1, min(radius, w // 2, h // 2))
    x2, y2 = x + w, y + h
    cv2.line(frame, (x+radius, y), (x2-radius, y), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (x+radius, y2), (x2-radius, y2), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (x, y+radius), (x, y2-radius), color, thickness, cv2.LINE_AA)
    cv2.line(frame, (x2, y+radius), (x2, y2-radius), color, thickness, cv2.LINE_AA)
    cv2.ellipse(frame, (x+radius, y+radius), (radius, radius), 180, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(frame, (x2-radius, y+radius), (radius, radius), 270, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(frame, (x+radius, y2-radius), (radius, radius), 90, 0, 90, color, thickness, cv2.LINE_AA)
    cv2.ellipse(frame, (x2-radius, y2-radius), (radius, radius), 0, 0, 90, color, thickness, cv2.LINE_AA)


def frosted_panel(frame, x, y, w, h, radius=24, blur_ksize=21, tint_alpha=0.35,
                   tint_color=GLASS_TINT, border_color=None, border_thickness=1):
    """Core visionOS 'glass card': blurs its own ROI, tints it translucently,
    gives it a rounded border and a soft drop shadow. Only blurs/tints what's
    already been drawn in that region this frame (our own canvas), not the
    real desktop behind the click-through window.
    """
    x, y, w, h = int(x), int(y), int(w), int(h)
    fh, fw = frame.shape[:2]
    x = max(0, x)
    y = max(0, y)
    w = min(w, fw - x)
    h = min(h, fh - y)
    if w <= 4 or h <= 4:
        return

    # Soft drop shadow, offset down-right
    shadow_offset = 6
    sx, sy = x + shadow_offset, y + shadow_offset
    sw, sh = min(w, fw - sx), min(h, fh - sy)
    if sw > 4 and sh > 4:
        shadow_mask = _rounded_rect_mask(sw, sh, radius)
        alpha_s = (shadow_mask.astype(np.float32) / 255.0 * 0.35)[..., None]
        shadow_roi = frame[sy:sy+sh, sx:sx+sw].astype(np.float32)
        frame[sy:sy+sh, sx:sx+sw] = (shadow_roi * (1 - alpha_s)).astype(np.uint8)

    roi = frame[y:y+h, x:x+w]
    k = blur_ksize if blur_ksize % 2 == 1 else blur_ksize + 1
    blurred = cv2.GaussianBlur(roi, (k, k), 0)

    tint = np.full_like(roi, tint_color, dtype=np.uint8)
    glass = cv2.addWeighted(blurred, 1 - tint_alpha, tint, tint_alpha, 0)

    mask_f = (_rounded_rect_mask(w, h, radius).astype(np.float32) / 255.0)[..., None]
    blended = (glass.astype(np.float32) * mask_f + roi.astype(np.float32) * (1 - mask_f)).astype(np.uint8)
    frame[y:y+h, x:x+w] = blended

    _draw_rounded_border(frame, x, y, w, h, radius, border_color or DIM_TEXT, border_thickness)


def draw_glass_button(frame, x, y, w, h, label, hovered=False, selected=False, radius=14):
    """Rectangular glass button (window thumbnails, settings shortcuts)."""
    tint_alpha = 0.5 if selected else (0.38 if hovered else 0.24)
    tint_color = ACCENT if selected else GLASS_TINT
    border_color = ACCENT if selected else (GLOW if hovered else DIM_TEXT)
    border_thickness = 2 if (hovered or selected) else 1

    frosted_panel(frame, x, y, w, h, radius=radius, blur_ksize=15, tint_alpha=tint_alpha,
                  tint_color=tint_color, border_color=border_color, border_thickness=border_thickness)

    text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)[0]
    tx = int(x) + max(4, (int(w) - text_size[0]) // 2)
    ty = int(y) + (int(h) + text_size[1]) // 2
    cv2.putText(frame, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
               DARK_TEXT if selected else WHITE, 1, cv2.LINE_AA)


def draw_dock_icon(frame, center, radius, glyph_text, hovered=False, selected=False):
    """Circular floating dock icon (Volume/Apps/WiFi/Bluetooth), visionOS Home-View style."""
    cx, cy = int(center[0]), int(center[1])
    r = int(radius * (1.15 if hovered else 1.0))

    overlay = frame.copy()
    cv2.circle(overlay, (cx + 3, cy + 4), r, (0, 0, 0), -1, lineType=cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.25, frame, 0.75, 0, dst=frame)

    fill_color = ACCENT if selected else GLASS_TINT
    fill_alpha = 0.55 if selected else (0.4 if hovered else 0.22)
    overlay = frame.copy()
    cv2.circle(overlay, (cx, cy), r, fill_color, -1, lineType=cv2.LINE_AA)
    cv2.addWeighted(overlay, fill_alpha, frame, 1 - fill_alpha, 0, dst=frame)

    border_color = ACCENT if selected else (GLOW if hovered else DIM_TEXT)
    cv2.circle(frame, (cx, cy), r, border_color, 2 if (hovered or selected) else 1, lineType=cv2.LINE_AA)

    text_size = cv2.getTextSize(glyph_text, cv2.FONT_HERSHEY_DUPLEX, 0.5, 1)[0]
    cv2.putText(frame, glyph_text, (cx - text_size[0]//2, cy + text_size[1]//2),
               cv2.FONT_HERSHEY_DUPLEX, 0.5, DARK_TEXT if selected else WHITE, 1, cv2.LINE_AA)


def draw_focus_cursor(frame, pos, pinching=False):
    """Small soft glow ring at the fingertip -- stands in for visionOS's (invisible) gaze point."""
    cx, cy = int(pos[0]), int(pos[1])
    radius = 10 if pinching else 14
    color = ACCENT if pinching else GLOW

    overlay = frame.copy()
    cv2.circle(overlay, (cx, cy), radius + 6, color, -1, lineType=cv2.LINE_AA)
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, dst=frame)

    cv2.circle(frame, (cx, cy), radius, color, 2, lineType=cv2.LINE_AA)
    if pinching:
        cv2.circle(frame, (cx, cy), 3, color, -1, lineType=cv2.LINE_AA)


def draw_countdown_ring(frame, center, remaining, total):
    """Glass countdown ring shown during the palm-close grace period."""
    cx, cy = int(center[0]), int(center[1])
    radius = 40
    thickness = 5
    fraction = max(0.0, min(1.0, remaining / total))

    cv2.circle(frame, (cx, cy), radius, (90, 90, 90), thickness, lineType=cv2.LINE_AA)
    end_angle = -90 + 360 * fraction
    cv2.ellipse(frame, (cx, cy), (radius, radius), 0, -90, end_angle, GLOW, thickness, lineType=cv2.LINE_AA)

    label = f"{remaining:.1f}s"
    label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
    cv2.putText(frame, label, (cx - label_size[0]//2, cy + label_size[1]//2),
               cv2.FONT_HERSHEY_SIMPLEX, 0.55, WHITE, 2, cv2.LINE_AA)

    hint = "Open palm to cancel"
    hint_size = cv2.getTextSize(hint, cv2.FONT_HERSHEY_SIMPLEX, 0.42, 1)[0]
    cv2.putText(frame, hint, (cx - hint_size[0]//2, cy + radius + 22),
               cv2.FONT_HERSHEY_SIMPLEX, 0.42, DIM_TEXT, 1, cv2.LINE_AA)
