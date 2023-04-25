from audio_encoder.audio_encoders.base import BaseAudioEncoder
from audio_encoder.media_info.parse_media import MediainfoParser
from audio_encoder.enums.shared import ProgressMode, StereoDownmix
from audio_encoder.enums.dd import DolbyDigitalChannels
from pathlib import Path
import shutil


class DDEncoderDEE(BaseAudioEncoder):
    def __init__(self, payload: object):
        super().__init__()
        self.payload = payload
        self.audio_track_info = MediainfoParser().get_track_by_id(
            r"C:\Users\jlw_4\OneDrive\Desktop\testing dre\Ant-Man.2015.UHD.BluRay.Subbed.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX-FraMeSToR.mkv",
            1,
        )
        
        # convert for dee
        self.fps = self._get_fps()
        

    def _get_fps(self):
        accepted_choices = {
            "23.976",
            "24",
            "25",
            "29.97",
            "30",
            "48",
            "50",
            "59.94",
            "60",
        }
        fps = "not_indicated"
        str_fps = str(self.payload.fps)
        if str_fps in accepted_choices:
            fps = str_fps
        return fps

        # print(vars(self.audio_track_info))

        # print(vars(self.payload))
        # self.audio_track_info = MediainfoParser().get_track_by_id("INPUT", 1)
