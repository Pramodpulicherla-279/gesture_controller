import cv2
import numpy as np

class EffectsProcessor:
    def __init__(self, effect_name):
        self.effect_name = effect_name
        self.effects = {
            'xray': self._apply_xray_effect,
            'technical': self._apply_technical_effect
        }
        
    def process_frame(self, frame, gesture_controller, volume_controller):
        try:
            if frame is None or frame.size == 0:
                return self._create_blank_frame(640, 480)
                
            # Apply selected effect
            effect_func = self.effects.get(self.effect_name, self._default_effect)
            processed_frame = effect_func(frame.copy())
            
            # Process gestures if frame is valid
            results = gesture_controller.process_frame(processed_frame)
            if results and results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    gesture_controller.draw_landmarks(processed_frame, hand_landmarks)
            
            return processed_frame
            
        except Exception as e:
            print(f"Error in effect processing: {e}")
            return frame.copy() if frame is not None else self._create_blank_frame(640, 480)
    
    def _create_blank_frame(self, width, height):
        return np.zeros((height, width, 3), dtype=np.uint8)
    
    def _default_effect(self, frame):
        return frame
    
    def _apply_xray_effect(self, frame):
        lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        l = clahe.apply(l)
        lab = cv2.merge((l, a, b))
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    
    def _apply_technical_effect(self, frame):
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY_INV)
        contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        output = np.zeros_like(frame)
        cv2.drawContours(output, contours, -1, (0, 255, 0), 1)
        return output