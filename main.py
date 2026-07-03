import cv2
import argparse
import threading
import numpy as np
import time
import ctypes
import win32gui
from core.gesture_controller import GestureController
from core.volume_controller import VolumeController
from core.window_controller import WindowController
from utils.system_tray import create_system_tray
from utils.helpers import load_config

# Constants for display dimensions
DISPLAY_WIDTH = 840
DISPLAY_HEIGHT = 680

def calculate_distance(point1, point2):
    """Calculate Euclidean distance between two points"""
    return np.sqrt((point1[0]-point2[0])**2 + (point1[1]-point2[1])**2)

def set_window_transparency(hwnd, opacity):
    """Set window transparency (0-255)"""
    try:
        ex_style = ctypes.windll.user32.GetWindowLongA(hwnd, -20)
        ctypes.windll.user32.SetWindowLongA(hwnd, -20, ex_style | 0x80000)
        ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, opacity, 0x2)
    except Exception as e:
        print(f"Couldn't set transparency: {e}")

def draw_hand_landmarks_3d(image_shape, landmarks, color=(0, 255, 0)):
    """Draw 3D-like hand landmarks on black background"""
    schematic = np.zeros((image_shape[0], image_shape[1], 3), dtype=np.uint8)
    
    if landmarks is None:
        return schematic
    
    # Define connections between landmarks (finger bones)
    connections = [
        (0, 1), (1, 2), (2, 3), (3, 4),  # Thumb
        (0, 5), (5, 6), (6, 7), (7, 8),  # Index
        (0, 9), (9, 10), (10, 11), (11, 12),  # Middle
        (0, 13), (13, 14), (14, 15), (15, 16),  # Ring
        (0, 17), (17, 18), (18, 19), (19, 20)  # Pinky
    ]
    
    # Define palm connections for more 3D feel
    palm_connections = [
        (0, 1), (0, 5), (0, 9), (0, 13), (0, 17),
        (5, 9), (9, 13), (13, 17)
    ]
    
    # Draw palm connections first (thicker lines)
    for connection in palm_connections:
        start = landmarks.landmark[connection[0]]
        end = landmarks.landmark[connection[1]]
        start_pos = (int(start.x * image_shape[1]), int(start.y * image_shape[0]))
        end_pos = (int(end.x * image_shape[1]), int(end.y * image_shape[0]))
        cv2.line(schematic, start_pos, end_pos, (color[0]//2, color[1]//2, color[2]//2), 3)
    
    # Draw finger connections with varying thickness for depth effect
    for connection in connections:
        start = landmarks.landmark[connection[0]]
        end = landmarks.landmark[connection[1]]
        start_pos = (int(start.x * image_shape[1]), int(start.y * image_shape[0]))
        end_pos = (int(end.x * image_shape[1]), int(end.y * image_shape[0]))
        
        # Calculate z-depth based on landmark z coordinate (assuming z is normalized)
        z_depth = (start.z + end.z) / 2
        thickness = max(1, int(3 * (1 - z_depth * 2)))  # Adjust thickness based on depth
        
        cv2.line(schematic, start_pos, end_pos, color, thickness)
    
    # Draw landmarks with size based on depth
    for i, landmark in enumerate(landmarks.landmark):
        pos = (int(landmark.x * image_shape[1]), int(landmark.y * image_shape[0]))
        radius = max(3, int(8 * (1 - landmark.z * 2)))  # Bigger for closer points
        
        # Use different colors for different parts of the hand
        if i == 0:  # Wrist
            landmark_color = (200, 200, 0)
        elif i in [4, 8, 12, 16, 20]:  # Fingertips
            landmark_color = (0, 200, 200)
        elif i % 4 == 0:  # Finger bases
            landmark_color = (200, 0, 200)
        else:  # Other joints
            landmark_color = color
        
        # Draw outer circle for 3D effect
        cv2.circle(schematic, pos, radius + 2, (50, 50, 50), -1)
        cv2.circle(schematic, pos, radius, landmark_color, -1)
        
        # Add highlight for 3D effect
        highlight_pos = (pos[0] - radius//3, pos[1] - radius//3)
        cv2.circle(schematic, highlight_pos, radius//3, (255, 255, 255), -1)
    
    return schematic

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
    
    # Set window to stay on top
    cv2.setWindowProperty('Gesture Control System', cv2.WND_PROP_TOPMOST, 1)
    
    # Set window transparency to 20%
    opacity_percent = 20
    hwnd = win32gui.FindWindow(None, 'Gesture Control System')
    set_window_transparency(hwnd, int(255 * opacity_percent / 100))

    # Control states
    volume_level = volume_controller.get_volume()
    is_dragging = False
    volume_bar_rect = (20, 20, 600, 30)
    last_click_time = 0
    click_cooldown = 0.5  # seconds
    
    # Cache for window previews
    preview_cache = []
    last_cache_update = 0
    cache_cooldown = 2.0  # seconds

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        # Create a black background with consistent dimensions
        display_frame = np.zeros((DISPLAY_HEIGHT, DISPLAY_WIDTH, 3), dtype=np.uint8)
        current_time = time.time()
        
        try:
            # Process the original frame (not flipped)
            results = gesture_controller.process_frame(frame)
            index_tip = None
            thumb_tip = None
            
            if results and results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    # Draw 3D hand landmarks
                    hand_3d = draw_hand_landmarks_3d((DISPLAY_HEIGHT, DISPLAY_WIDTH), hand_landmarks)
                    
                    # Flip the hand 3d horizontally to match mirror-like movement
                    hand_3d = cv2.flip(hand_3d, 1)
                    
                    # Add the hand 3d to our display frame
                    display_frame = cv2.add(display_frame, hand_3d)
                    
                    landmarks = hand_landmarks.landmark
                    
                    # Get finger positions (using display dimensions)
                    # Flip the x-coordinate to match the display
                    index_tip = (DISPLAY_WIDTH - int(landmarks[8].x * DISPLAY_WIDTH), 
                                int(landmarks[8].y * DISPLAY_HEIGHT))
                    thumb_tip = (DISPLAY_WIDTH - int(landmarks[4].x * DISPLAY_WIDTH), 
                                int(landmarks[4].y * DISPLAY_HEIGHT))
                    
                    # Visual connection between index and thumb
                    if index_tip and thumb_tip:
                        cv2.line(display_frame, index_tip, thumb_tip, (255, 0, 0), 2)

            # Update preview cache if needed
            if current_time - last_cache_update > cache_cooldown:
                preview_cache = window_controller.get_windows()
                last_cache_update = current_time

            # Display cached window previews
            preview_width = 120
            preview_height = 80
            margin = 10
            
            for i, win in enumerate(preview_cache):
                x = DISPLAY_WIDTH - preview_width - margin
                y = margin + i * (preview_height + margin)
                
                # Draw preview background
                cv2.rectangle(display_frame, (x, y), (x+preview_width, y+preview_height), 
                             (50, 50, 50), -1)
                cv2.rectangle(display_frame, (x, y), (x+preview_width, y+preview_height), 
                             (255, 255, 255), 1)
                
                # Display window title
                title = win.title[:15] + "..." if len(win.title) > 15 else win.title
                cv2.putText(display_frame, title, (x+5, y+15), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                
                # Check if clicked (index finger in preview area)
                if (index_tip and 
                    x <= index_tip[0] <= x+preview_width and 
                    y <= index_tip[1] <= y+preview_height):
                    
                    cv2.rectangle(display_frame, (x, y), (x+preview_width, y+preview_height), 
                                 (0, 255, 0), 2)
                    
                    # Only activate if we're not dragging and cooldown has passed
                    if (not is_dragging and 
                        current_time - last_click_time > click_cooldown):
                        window_controller.activate_window(i)
                        last_click_time = current_time

            # Volume control
            bar_x, bar_y, bar_w, bar_h = volume_bar_rect
            cv2.rectangle(display_frame, (bar_x, bar_y), (bar_x+bar_w, bar_y+bar_h), (50,50,50), -1)
            filled = int((volume_level/100)*bar_w)
            cv2.rectangle(display_frame, (bar_x, bar_y), (bar_x+filled, bar_y+bar_h), (0,200,0), -1)
            cv2.rectangle(display_frame, (bar_x, bar_y), (bar_x+bar_w, bar_y+bar_h), (255,255,255), 2)
            knob_x = bar_x + filled
            cv2.circle(display_frame, (knob_x, bar_y+bar_h//2), 15, (0,0,255), -1)
            cv2.putText(display_frame, f"{volume_level}%", (bar_x+bar_w+10, bar_y+bar_h), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255,255,255), 2)

            if index_tip:
                near_knob = (abs(index_tip[0]-knob_x) < 30 and abs(index_tip[1]-(bar_y+bar_h//2)) < 30)
                near_bar_track = abs(index_tip[1]-(bar_y+bar_h//2)) < 30

                if near_knob:
                    is_dragging = True
                elif not near_bar_track:
                    # Finger has moved away from the slider track (e.g. toward a
                    # window preview) -- release the drag so it doesn't keep
                    # eating every subsequent finger movement.
                    is_dragging = False

                if is_dragging:
                    vol = int(((index_tip[0]-bar_x)/bar_w)*100)
                    vol = max(0, min(100, vol))
                    if vol != volume_level:
                        volume_controller.set_volume(vol)
                        volume_level = vol

            if not index_tip and is_dragging:
                is_dragging = False

            # Instructions
            instructions = [
                "Volume: Drag the red knob with index finger",
                "Window Control:",
                "  - Point at preview → Activate window",
                "Press 'q' to quit"
            ]
            
            for i, text in enumerate(instructions):
                cv2.putText(display_frame, text, (20, DISPLAY_HEIGHT - 100 + i*20),
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