from audio_encoder.audio_encoders.base import BaseAudioEncoder
from audio_encoder.media_info.parse_media import MediainfoParser
from audio_encoder.enums.shared import ProgressMode, StereoDownmix
from audio_encoder.enums.dd import DolbyDigitalChannels
from pathlib import Path
import shutil



class DDEncoder(BaseAudioEncoder):
    def __init__(self, payload: object):
        super().__init__()
        
        # print(vars(payload))
        # self.audio_track_info = MediainfoParser().get_track_by_id("INPUT", 1)