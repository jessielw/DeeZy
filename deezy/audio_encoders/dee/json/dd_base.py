"""
All 'None' values MUST be replaced during generation..
"""

dd_base = {
    "job_config": {
        "input": {
            "audio": {
                "wav": {
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
                "pcm_to_ddp": {
                    "-version": "3",
                    "loudness": {
                        "measure_only": {
                            "metering_mode": None,  # str
                            "dialogue_intelligence": None,  # bool
                            "speech_threshold": None,  # int
                        }
                    },
                    "encoder_mode": None,  # str [dd | ddp]
                    "bitstream_mode": "complete_main",
                    "downmix_config": None,  # str
                    "data_rate": None,  # int
                    "timecode_frame_rate": None,  # str
                    "start": "first_frame_of_action",
                    "end": "end_of_file",
                    "time_base": "file_position",
                    "prepend_silence_duration": "0",
                    "append_silence_duration": "0",
                    "lfe_on": "true",
                    "dolby_surround_mode": "not_indicated",
                    "dolby_surround_ex_mode": "no",
                    "user_data": "-1",
                    "drc": {
                        "line_mode_drc_profile": None,  # str
                        "rf_mode_drc_profile": None,  # str
                    },
                    "lfe_lowpass_filter": None,  # bool
                    "surround_90_degree_phase_shift": None,  # bool
                    "surround_3db_attenuation": None,  # bool
                    "downmix": {
                        "loro_center_mix_level": None,  # str
                        "loro_surround_mix_level": None,  # str
                        "ltrt_center_mix_level": None,  # str
                        "ltrt_surround_mix_level": None,  # str
                        "preferred_downmix_mode": None,  # str
                    },
                    "allow_hybrid_downmix": "false",
                    "embedded_timecodes": {
                        "starting_timecode": "off",  # needs to always be off for compatibility and like ffmpeg
                        "frame_rate": "auto",
                    },
                    "custom_dialnorm": None,  # str[int] (-1 - -31) but "0" disables it
                }
            }
        },
        "output": {  # we'll remove ac3/ec3 depending on the flow
            "ac3": {
                "-version": "1",
                "file_name": None,  # str (full windows style double quoted path)
                "storage": {"local_multi_path": {"path": "-"}},
            },
            "ec3": {
                "-version": "1",
                "file_name": None,  # str (full windows style double quoted path)
                "storage": {"local_multi_path": {"path": "-"}},
            },
        },
        "misc": {
            "temp_dir": {
                "clean_temp": None,  # "true" or "false" string bool
                "path": None,  # str (full windows style double quoted path)
            }
        },
    }
}
