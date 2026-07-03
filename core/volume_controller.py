from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL
import time

class VolumeController:
    def __init__(self):
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(
            IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        self.volume = cast(interface, POINTER(IAudioEndpointVolume))
        self.vol_range = self.volume.GetVolumeRange()
        self.min_vol, self.max_vol = self.vol_range[0], self.vol_range[1]
        self.last_volume = self.get_volume()
        self.last_update_time = time.time()

    def set_volume(self, level):
        """Set volume level (0-100) with immediate feedback"""
        vol = self.min_vol + (self.max_vol - self.min_vol) * (level / 100)
        self.volume.SetMasterVolumeLevel(vol, None)
        self.last_volume = level
        self.last_update_time = time.time()

    def get_volume(self):
        """Get current volume level (0-100) with rounding to nearest integer"""
        vol_scalar = self.volume.GetMasterVolumeLevelScalar()
        return int(round(vol_scalar * 100))  # Rounded to nearest percent

    def is_volume_changed_externally(self):
        """Check if volume was changed outside our application"""
        current_vol = self.get_volume()
        if current_vol != self.last_volume:
            self.last_volume = current_vol
            return True
        return False