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
        self.thresholds = config.get('gesture_thresholds', {})

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

    def is_palm_open(self, hand_landmarks):
        """True when index/middle/ring/pinky are extended and spread from the wrist (open palm)"""
        try:
            landmarks = hand_landmarks.landmark
            wrist = landmarks[0]
            finger_tips = (8, 12, 16, 20)
            finger_pips = (6, 10, 14, 18)

            extended_count = 0
            total_reach = 0.0
            for tip_idx, pip_idx in zip(finger_tips, finger_pips):
                tip = landmarks[tip_idx]
                pip = landmarks[pip_idx]
                if tip.y < pip.y:  # tip above pip joint => finger pointing up/extended
                    extended_count += 1
                total_reach += ((tip.x - wrist.x) ** 2 + (tip.y - wrist.y) ** 2) ** 0.5

            avg_reach = total_reach / len(finger_tips)
            open_threshold = self.thresholds.get('open', 0.1)
            return extended_count >= 3 and avg_reach > open_threshold
        except Exception as e:
            print(f"Error checking palm open: {e}")
            return False

    @staticmethod
    def _pinch_distance(hand_landmarks, tip_idx):
        landmarks = hand_landmarks.landmark
        thumb_tip = landmarks[4]
        tip = landmarks[tip_idx]
        return ((thumb_tip.x - tip.x) ** 2 + (thumb_tip.y - tip.y) ** 2) ** 0.5

    def is_pinching(self, hand_landmarks):
        """True when thumb tip and index tip are touching (left-click / confirm gesture)"""
        try:
            threshold = self.thresholds.get('pinch', 0.05)
            return self._pinch_distance(hand_landmarks, 8) < threshold
        except Exception as e:
            print(f"Error checking pinch: {e}")
            return False

    def is_right_click_pinch(self, hand_landmarks):
        """True when thumb tip and middle finger tip are touching (right-click gesture)"""
        try:
            threshold = self.thresholds.get('pinch', 0.05)
            return self._pinch_distance(hand_landmarks, 12) < threshold
        except Exception as e:
            print(f"Error checking right-click pinch: {e}")
            return False

    def is_scroll_pinch(self, hand_landmarks):
        """True when thumb tip and ring finger tip are touching (hold + move vertically to scroll)"""
        try:
            threshold = self.thresholds.get('pinch', 0.05)
            return self._pinch_distance(hand_landmarks, 16) < threshold
        except Exception as e:
            print(f"Error checking scroll pinch: {e}")
            return False