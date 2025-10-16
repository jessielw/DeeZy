from pathlib import Path

from platformdirs import user_config_dir

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
# Path to FFmpeg executable (leave empty for auto-detection)
ffmpeg = ""  
# Path to Dolby Encoding Engine (DEE) executable
dee = ""     
# Path to truehdd executable
truehdd = "" 

[global_defaults]
# Keep temporary files after processing
keep_temp = false
# Custom temporary directory (leave empty for system default)      
temp_dir = ""
# Default audio track index to process
track_index = 0
# Directory for DeeZy working files (logs, batch-results). Empty = default beside executable
working_dir = ""
# Enable batch JSON summary output by default
batch_summary_output = false
# When set, encoded outputs will be placed into this directory
batch_output_dir = ""
# Default output filename template. Leave empty to use automatic naming.
# Supported tokens: {title},{year},{stem},{stem-cleaned},{source},{lang},{channels},{worker},{delay},{opt-delay}
output_template = ""
# Default maximum parallel jobs for batch processing
max_parallel = 1
# Maximum number of log files to keep in working logs/ (oldest removed)       
max_logs = 50
# Maximum number of batch-results JSON files to keep (oldest removed)    
max_batch_results = 50
# Overwrite existing outputs when encoding. When false, existing outputs will cause jobs to be skipped.
overwrite = false
# Maximum random jitter (ms) applied before heavy phases (FFmpeg/DEE/TrueHDD). 0 = disabled.
jitter_ms = 0
# Per-phase concurrency limits. Set to 0 to inherit the value of `max_parallel`.
# These allow fine-grained tuning when some phases are more/less intensive.
limit_ffmpeg = 0
limit_dee = 0
limit_truehdd = 0
# When input is an elementary stream, parse delay from filename and strip it when True
parse_elementary_delay = false
# Write logs to file by default for each job
log_to_file = false
# Disable progress bars by default
no_progress_bars = false
# Dynamic range compression for line mode
drc_line_mode = "film_light"
# Dynamic range compression for RF mode
drc_rf_mode = "film_light"
# Custom dialnorm value (0 = auto-detect) 
custom_dialnorm = 0
# metering_mode: handled per-format (DD/DDP=1770_3, Atmos=1770_4)
# Enable dialogue intelligence
dialogue_intelligence = true
# Speech detection threshold percentage
speech_threshold = 20
# Stereo downmix method
stereo_down_mix = "loro"     
 # Lt/Rt center channel downmix level
lt_rt_center = "-3"        
# Lt/Rt surround channels downmix level 
lt_rt_surround = "-3"   
# Lo/Ro center channel downmix level     
lo_ro_center = "-3"      
# Lo/Ro surround channels downmix level    
lo_ro_surround = "-3"        

[default_bitrates]
# Default bitrates for Dolby Digital (AC-3)
[default_bitrates.dd]
mono = 192     # DD 1.0
stereo = 224   # DD 2.0
surround = 448 # DD 5.1

# Optional per-source defaults for Dolby Digital (AC-3)
# Uncomment to opt-in to per-source defaults keyed by source channel count.
# Values below are examples derived from the encoder enums (MONO/STEREO/SURROUND)
# and are commented out so they're not active by default.
#[default_source_bitrates.dd]
# ch_1 = 192
# ch_2 = 224 
# ch_3 = 224  
# ch_4 = 224
# ch_5 = 224
# ch_6 = 448  
# ch_7 = 448 
# ch_8 = 448

# NOTES:
# The optional [default_source_bitrates.<codec>] sections let you opt-in to per-source
# default bitrates keyed by source channel count. Keys should be named ch_1..ch_8 (lowercase
# preferred). The encoder will look under this section when no bitrate is supplied on the
# CLI/preset and will use the value for the detected source channel count. If the value
# found in the config is not an allowed bitrate for the chosen encoding settings, the
# encoder will pick the closest allowed bitrate from its internal choices.
#
# Supported codecs:
#  - dd, ddp: support ch_1..ch_8
#  - ac4: meaningful only for channels 6..8 (use ch_6..ch_8)
#

# Default bitrates for Dolby Digital Plus (E-AC-3)
[default_bitrates.ddp]
mono = 64        # DDP 1.0
stereo = 128     # DDP 2.0
surround = 192   # DDP 5.1
surroundex = 384 # DDP 7.1

# Optional per-source defaults for Dolby Digital Plus (E-AC-3)
# Uncomment to opt-in. Example values derived from the DDP enum defaults:
# mono=64, stereo=128, surround=192, surroundex=384
#[default_source_bitrates.ddp]
# ch_1 = 64 
# ch_2 = 128
# ch_3 = 128 
# ch_4 = 128
# ch_5 = 128
# ch_6 = 192   
# ch_7 = 192 
# ch_8 = 384

# Default bitrates for Dolby Digital Plus Bluray
[default_bitrates.ddp-bluray]
surroundex = 1280 # DDP Bluray 7.1

# Default bitrates for Dolby Atmos
[default_bitrates.atmos]
streaming = 448 # Atmos Streaming
bluray = 1280    # Atmos Bluray

# Default bitrates for AC4
[default_bitrates.ac4]
immersive_stereo = 256 # AC4 Immersive Stereo

# Optional per-source defaults for AC4
# AC4 encoding choices include 256 as a common default. AC4 is only meaningful
# for immersive multi-channel sources (6..8) in many workflows; these are examples.
# Uncomment to opt-in.
#[default_source_bitrates.ac4]
# ch_6 = 256
# ch_6_atmos = 320
# ch_7 = 256
# ch_7_atmos = 320
# ch_8 = 256
# ch_8_atmos = 320

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
    """Get the default configuration file path.

            Search order used by ConfigManager.load_config when no explicit path is
            provided:
                    1. Current working directory: allows per-project configs (existing behavior)
                    2. User config directory: platform-specific stable location
                       (e.g., %APPDATA%\\deezy\\deezy-conf.toml on Windows)
                    3. Working directory beside executable (for bundled/exe usage)

    This function returns the user config path which is the recommended
    location for persisted user-wide configuration. ConfigManager.load_config
    will still check the current working directory first.
    """

    # Prefer a single `deezy` folder on Windows (e.g. %LOCALAPPDATA%\deezy\deezy-conf.toml)
    # while preserving the platform default on other OSes.
    base = Path(user_config_dir("deezy"))
    try:
        import sys

        if sys.platform.startswith("win"):
            cfg_dir = base.parent
        else:
            cfg_dir = base
    except Exception:
        cfg_dir = base

    return cfg_dir / "deezy-conf.toml"
