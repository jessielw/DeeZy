from audio_encoder.payloads.shared import BaseArgsPayload


class DDPPayload(BaseArgsPayload):
    channels = None
    normalize = None
