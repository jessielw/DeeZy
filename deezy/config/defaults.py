from pathlib import Path

from deezy.utils.utils import get_working_dir

# fmt: off
CONF_DEFAULT = """\
# DeeZy Configuration File
# 
# This file contains default values and presets for the DeeZy audio encoding tool.
#
# ARGUMENT MAPPING:
# CLI arguments like '--arg-name' are converted to config keys like 'arg_name'
# For example:
#   --drc-line-mode     becomes     drc_line_mode
#   --custom-dialnorm   becomes     custom_dialnorm  
#   --lt-rt-center      becomes     lt_rt_center
#
# SECTIONS:
# [dependencies]     - Paths to external tools (ffmpeg, dee, truehd)
# [global_defaults]  - Default values applied to all encoding commands
# [default_bitrates] - Automatic bitrate selection by format and channel layout
# [presets]          - Named command templates for common encoding scenarios
#
# VALUES:
# - String values: Use quotes for text values
# - Boolean values: true/false (lowercase)  
# - Numeric values: Plain numbers (no quotes)
# - Empty values: Use "" for empty strings
#
# CLI arguments always override config defaults.
# Preset arguments can be overridden by additional CLI flags.

[dependencies]
ffmpeg = ""  # Path to FFmpeg executable (leave empty for auto-detection)
dee = ""     # Path to Dolby Encoding Engine (DEE) executable
truehdd = "" # Path to TrueHD executable  

[global_defaults]
keep_temp = false            # Keep temporary files after processing
temp_dir = ""                # Custom temporary directory (leave empty for system default)
track_index = 0              # Default audio track index to process
drc_line_mode = "film_light" # Dynamic range compression for line mode
drc_rf_mode = "film_light"   # Dynamic range compression for RF mode  
custom_dialnorm = 0          # Custom dialnorm value (0 = auto-detect)
# metering_mode: handled per-format (DD/DDP=1770_3, Atmos=1770_4)
dialogue_intelligence = true # Enable dialogue intelligence
speech_threshold = 20        # Speech detection threshold percentage
stereo_down_mix = "loro"     # Stereo downmix method
lt_rt_center = "-3"          # Lt/Rt center channel downmix level
lt_rt_surround = "-3"        # Lt/Rt surround channels downmix level
lo_ro_center = "-3"          # Lo/Ro center channel downmix level
lo_ro_surround = "-3"        # Lo/Ro surround channels downmix level

[default_bitrates]
# Default bitrates for Dolby Digital (AC-3)
[default_bitrates.dd]
mono = 192     # DD 1.0
stereo = 224   # DD 2.0
surround = 448 # DD 5.1

# Default bitrates for Dolby Digital Plus (E-AC-3)
[default_bitrates.ddp]
mono = 64        # DDP 1.0
stereo = 128     # DDP 2.0
surround = 192   # DDP 5.1
surroundex = 384 # DDP 7.1

# Default bitrates for Dolby Digital Plus Bluray
[default_bitrates.ddp_bluray]
surroundex = 384 # DDP Bluray 7.1

# Default bitrates for Dolby Atmos
[default_bitrates.atmos]
streaming = 448 # Atmos Streaming
bluray = 448    # Atmos Bluray

[presets]
# Example presets - customize as needed
streaming_ddp = "encode ddp --channels surround --bitrate 448"
bluray_dd = "encode dd --channels surround --bitrate 640"
auto_stereo_ddp = "encode ddp --channels stereo"
streaming_atmos = "encode atmos --atmos-mode streaming"
ac4_stereo = "encode ac4 --bitrate 256"
"""
# fmt: on


def get_default_config_path() -> Path:
    """Get the default configuration file path."""
    return get_working_dir() / "deezy-conf.toml"
