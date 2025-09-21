"""
All 'None' values MUST be replaced during generation..
"""

atmos_base = {
    "job_config": {
        "input": {
            "audio": {
                "atmos_mezz": {
                    "-version": "1",
                    "file_name": None,  # str (full windows style double quoted path)
                    "timecode_frame_rate": None,  # str
                    "offset": "auto",
                    "ffoa": "auto",
                    "storage": {"local_multi_path": {"path": "-"}},
                }
            }
        },
        "filter": {
            "audio": {
                "encode_to_atmos_ddp": {
                    "-version": "1",
                    "loudness": {
                        "measure_only": {
                            "metering_mode": None,  # str
                            "dialogue_intelligence": None,  # bool
                            "speech_threshold": None,  # int
                        }
                    },
                    "data_rate": None,  # int
                    "timecode_frame_rate": None,  # str
                    "start": "first_frame_of_action",
                    "end": "end_of_file",
                    "time_base": "file_position",
                    "prepend_silence_duration": "0",
                    "append_silence_duration": "0",
                    "drc": {
                        "line_mode_drc_profile": None,  # str
                        "rf_mode_drc_profile": None,  # str
                    },
                    "downmix": {
                        "loro_center_mix_level": None,  # str
                        "loro_surround_mix_level": None,  # str
                        "ltrt_center_mix_level": None,  # str
                        "ltrt_surround_mix_level": None,  # str
                        "preferred_downmix_mode": None,  # str
                    },
                    "custom_trims": {
                        "surround_trim_5_1": "auto",
                        "height_trim_5_1": "auto",
                    },
                    "custom_dialnorm": None,  # str[int] (-1 - -31) but "0" disables it
                    # enable the below for atmos bluray 7.1
                    # "encoding_backend": "atmosprocessor",
                    # "encoder_mode": "bluray"
                }
            }
        },
        "output": {
            "ec3": {
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
