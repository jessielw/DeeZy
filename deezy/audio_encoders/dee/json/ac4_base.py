"""
All 'None' values MUST be replaced during generation..
"""

ac4_base = {
    "job_config": {
        "input": {
            "audio": {  # we'll remove 'wav' or 'atmos_mezz' depending on work flow
                "wav": {
                    "-version": "1",
                    "file_name": None,  # str (full windows style double quoted path)
                    "timecode_frame_rate": None,  # str
                    "offset": "auto",
                    "ffoa": "auto",
                    "storage": {"local_multi_path": {"path": "-"}},
                },
                "atmos_mezz": {
                    "-version": "1",
                    "file_name": None,  # str (full windows style double quoted path)
                    "timecode_frame_rate": None,  # str
                    "offset": "auto",
                    "ffoa": "auto",
                    "storage": {"local_multi_path": {"path": "-"}},
                },
            }
        },
        "filter": {
            "audio": {
                "encode_to_ims_ac4": {
                    "-version": "1",
                    "timecode_frame_rate": None,  # str
                    "start": "first_frame_of_action",
                    "end": "end_of_file",
                    "time_base": "file_position",
                    "prepend_silence_duration": "0",
                    "append_silence_duration": "0",
                    "loudness": {
                        "measure_only": {
                            "metering_mode": None,  # str
                            "dialogue_intelligence": None,  # bool
                            "speech_threshold": None,  # int
                        }
                    },
                    "data_rate": None,  # int
                    "ac4_frame_rate": None,  # str
                    "ims_legacy_presentation": None,  # str[bool], lowercase true or false
                    "iframe_interval": None,  # int
                    "language": "",
                    "encoding_profile": None,  # str
                    "drc": {
                        "ddp_drc_profile": None,  # str
                        "flat_panel_drc_profile": None,  # str
                        "home_theatre_drc_profile": None,  # str
                        "portable_hp_drc_profile": None,  # str
                        "portable_spkr_drc_profile": None,  # str
                    },
                }
            }
        },
        "output": {
            "ac4": {
                "-version": "1",
                "file_name": None,  # str (full windows style double quoted path)
                "storage": {"local_multi_path": {"path": "-"}},
            }
        },
        "misc": {
            "temp_dir": {
                "clean_temp": None,  # "true" or "false" string bool
                "path": None,  # str (full windows style double quoted path)
            }
        },
    }
}
