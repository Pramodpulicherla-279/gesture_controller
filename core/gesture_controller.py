import mediapipe as mp
import cv2

class GestureController:
    def __init__(self, config):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            max_num_hands=config.get('max_hands', 1),
            min_detection_confidence=config.get('detection_confidence', 0.7),
            min_tracking_confidence=config.get('tracking_confidence', 0.7)
        )
        self.mp_draw = mp.solutions.drawing_utils
        self.landmark_color = tuple(config.get('landmark_color', [0, 255, 255]))
        self.connection_color = tuple(config.get('connection_color', [255, 0, 255]))

    def process_frame(self, frame):
        if frame is None or frame.size == 0:
            return None
            
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            return self.hands.process(rgb_frame)
        except Exception as e:
            print(f"Error in gesture processing: {e}")
            return None

    def draw_landmarks(self, frame, hand_landmarks):
        try:
            self.mp_draw.draw_landmarks(
                frame, hand_landmarks, self.mp_hands.HAND_CONNECTIONS,
                landmark_drawing_spec=self.mp_draw.DrawingSpec(
                    color=self.landmark_color, thickness=2, circle_radius=3),
                connection_drawing_spec=self.mp_draw.DrawingSpec(
                    color=self.connection_color, thickness=2)
            )
            
            # Highlight index finger
            landmarks = hand_landmarks.landmark
            h, w, _ = frame.shape
            index_tip = (int(landmarks[8].x * w), int(landmarks[8].y * h))
            cv2.circle(frame, index_tip, 15, (0, 255, 255), -1)
            
        except Exception as e:
            print(f"Error drawing landmarks: {e}")