# DeeZy

A powerful, portable audio encoding tool built around the Dolby Encoding Engine (DEE) with support for Dolby Digital (DD), Dolby Digital Plus (DDP), DDP BluRay, and Dolby Atmos encoding.

## ✨ Key Features

- **🎵 Multiple Audio Formats**: Support for Dolby Digital (DD), Dolby Digital Plus (DDP), DDP BluRay, and Dolby Atmos
- **🔧 Portable**: No installation required - just download and run
- **⚙️ Smart Configuration**: TOML-based config system with customizable default bitrates and presets
- **🎛️ Flexible Encoding**: Automatic channel detection, smart bitrate defaults, and advanced audio processing
- **🌟 Atmos Support**: Full support for streaming and BluRay Atmos encoding
- **📁 Batch Processing**: Process multiple files or use glob patterns for bulk operations
- **🎚️ Advanced Controls**: Dynamic range compression, stereo downmix options, and loudness normalization
- **⚡ Smart Dependencies**: Auto-detection of tools with fallback to portable structure
- **🔍 Audio Analysis**: Built-in audio stream inspection and metadata display
- **🎯 Preset System**: Define custom encoding workflows for different use cases

## 📦 Installation

DeeZy is completely portable - no installation needed! Just download the binary for your platform.

### Option 1: System PATH (Recommended)

Add FFMPEG, DEE (Dolby Encoding Engine), and optionally TrueHDD to your system PATH, then use DeeZy anywhere.

### Option 2: Portable Structure

Create an `apps` folder beside the DeeZy executable:

```
deezy.exe (or deezy on Linux)
└── apps/
    ├── ffmpeg/
    │   └── ffmpeg.exe
    ├── dee/
    │   └── dee.exe
    └── truehdd/         # Only needed for Atmos encoding
        └── truehdd.exe
```

### Dependencies

- **FFMPEG** - Required for all operations
- **DEE (Dolby Encoding Engine)** - Required for DD/DDP encoding
- **[TrueHDD](https://github.com/truehdd/truehdd)** - Only required when encoding Atmos content

## ⚙️ Configuration System

DeeZy includes a powerful TOML-based configuration system that eliminates repetitive command-line arguments and allows you to set encoding defaults and create reusable presets.

### Quick Configuration Setup

```bash
# Generate a default configuration file
deezy config generate

# Check configuration status
deezy config info

# Use a custom config file
deezy --config my-config.toml encode ddp input.mkv

# Overwrite existing configuration
deezy config generate --overwrite
```

### Configuration File Structure

The configuration file (`deezy-conf.toml`) supports:

- **Tool dependency paths** (FFmpeg, DEE, TrueHD)
- **Global encoding defaults** applied to all formats
- **Default bitrates** per codec and channel layout
- **Format-specific settings** that override global defaults
- **Custom presets** for different workflows

```toml
[dependencies]
# Paths to external tools (leave empty for auto-detection)
ffmpeg = ""
dee = ""
truehd = ""

[global_defaults]
# Settings applied to all encoding formats
keep_temp = false
temp_dir = ""
track_index = 0
drc_line_mode = "film_light"
drc_rf_mode = "film_light"
custom_dialnorm = 0
metering_mode = "1770_3"
dialogue_intelligence = true
speech_threshold = 15
stereo_down_mix = "loro"

[default_bitrates]
# Customize default bitrates for each codec/channel combination
# These are used when no --bitrate is specified

[default_bitrates.dd]
mono = 192        # Dolby Digital 1.0
stereo = 224      # Dolby Digital 2.0
surround = 448    # Dolby Digital 5.1

[default_bitrates.ddp]
mono = 64         # Dolby Digital Plus 1.0
stereo = 128      # Dolby Digital Plus 2.0
surround = 192    # Dolby Digital Plus 5.1
surroundex = 384  # Dolby Digital Plus 7.1

[default_bitrates.atmos]
streaming = 448   # Dolby Atmos Streaming mode
bluray = 448      # Dolby Atmos Bluray mode

[presets]
# Define custom presets as command strings
streaming_ddp = "encode ddp --channels surround --bitrate 448"
bluray_atmos = "encode atmos --atmos-mode bluray --bitrate 768"
quick_stereo = "encode ddp --channels stereo --bitrate 192"
```

### Configuration Location

DeeZy looks for `deezy-conf.toml` beside the executable for portable usage. You can also specify a custom config file with `--config path/to/config.toml`.

### Priority System

Configuration values are applied in order of priority:
**CLI Arguments** > **Config Defaults** > **Format-Specific Defaults** > **Built-in Fallback Defaults**

- **CLI Arguments**: Any argument provided directly on the command line takes highest priority
- **Config Defaults**: Values from the `[global_defaults]` section of your config file
- **Format-Specific Defaults**: Smart defaults based on encoding format (e.g., DD/DDP use 1770-3 metering, Atmos uses 1770-4)
- **Built-in Fallback Defaults**: Hardcoded defaults when nothing else is configured

### Smart Defaults System

DeeZy automatically applies intelligent defaults based on the encoding format when arguments are not specified:

**Smart Default Bitrates** (based on codec and channel layout):

- **DD 5.1**: 448 kbps (configurable)
- **DDP Stereo**: 128 kbps (configurable)
- **DDP 5.1**: 192 kbps (configurable)
- **DDP 7.1**: 384 kbps (configurable)
- **Atmos Streaming**: 448 kbps (configurable)

**Smart Channel Defaults** (when `--channels` not specified):

- **DD**: AUTO (automatically detects best channel layout)
- **DDP**: AUTO (automatically detects best channel layout)
- **DDP-BluRay**: SURROUNDEX (7.1 for BluRay releases)
- **Atmos**: No channel argument (uses source layout)

**Smart Metering Mode Defaults** (when `--metering-mode` not specified):

- **DD/DDP**: 1770-3 (standard for traditional surround formats)
- **Atmos**: 1770-4 (supports advanced Atmos loudness requirements)

### Preset System

Create reusable encoding profiles for different workflows using simple command strings:

```bash
# Use a preset for encoding (format determined from preset)
deezy encode preset --name streaming_ddp input.mkv

# Override preset settings as needed
deezy encode preset --name bluray_atmos --bitrate 1024 input.mkv

# List available presets
deezy config info
```

### Preset Configuration

Presets are defined as command strings in the `[presets]` section of your config file. This makes them simple to create and understand:

```toml
[presets]
# Simple preset examples using command strings
streaming_ddp = "encode ddp --channels surround --bitrate 448"
bluray_dd = "encode dd --channels surround --bitrate 640"
auto_stereo_ddp = "encode ddp --channels stereo"
streaming_atmos = "encode atmos --atmos-mode streaming"

# Advanced presets with multiple options
high_quality_ddp = "encode ddp --channels surround --bitrate 768 --drc-line-mode music_standard"
custom_atmos = "encode atmos --atmos-mode bluray --bitrate 1024 --custom-dialnorm 5"
legacy_dd = "encode dd --channels surround --bitrate 448 --drc-line-mode film_light --metering-mode 1770_3"
```

**Preset Benefits:**

- **Simple format**: Just write the command as you would use it on the CLI
- **Easy to read**: Command strings are self-documenting
- **Override capable**: Add extra arguments when using the preset to override settings
- **Validation**: DeeZy validates preset commands and suggests fixes for errors

**Usage Examples:**

```bash
# Use preset as-is
deezy encode preset --name streaming_ddp input.mkv

# Override preset bitrate
deezy encode preset --name streaming_ddp --bitrate 640 input.mkv

# Use preset with additional options
deezy encode preset --name auto_stereo_ddp --keep-temp --output custom.ec3 input.mkv
```

### Benefits

**Before Configuration:**

```bash
deezy encode ddp --ffmpeg "C:/tools/ffmpeg.exe" --dee "C:/apps/dee.exe" --channels 6 --bitrate 448 --drc-line-mode film_light input.mkv
```

**After Configuration:**

```bash
deezy encode ddp input.mkv  # Uses smart defaults and your configured tools!
```

## 🚀 Quick Start

```bash
# Set up configuration once
deezy config generate

# Encode to Dolby Digital Plus with smart defaults
deezy encode ddp input.mkv

# Encode to Dolby Atmos
deezy encode atmos --atmos-mode streaming input.mkv

# Use a predefined preset
deezy encode preset --name streaming_ddp input.mkv

# Batch encode multiple files
deezy encode ddp *.mkv

# Get audio track information
deezy info input.mkv

# Check temp folder status
deezy temp info

# Clean old temp files
deezy temp clean
```

## 📋 Usage

### Basic Commands

```bash
# Show version
deezy --version

# Get help for any command
deezy encode ddp --help

# Find files using glob patterns
deezy find "**/*.mkv"

# Analyze audio streams
deezy info input.mkv

# Manage configuration
deezy config generate
```

### Global Options

| Option                 | Description                                           |
| ---------------------- | ----------------------------------------------------- |
| `--version`            | Show program version                                  |
| `--config CONFIG_FILE` | Path to configuration file (default: deezy-conf.toml) |
| `--log-level LEVEL`    | Set log level (critical, error, warning, info, debug) |
| `--log-to-file`        | Write log to file (input path with .log suffix)       |
| `--no-progress-bars`   | Disable progress bars                                 |
| `-h, --help`           | Show help message                                     |

### Main Commands

| Command             | Description                                  |
| ------------------- | -------------------------------------------- |
| `encode dd`         | Dolby Digital encoding                       |
| `encode ddp`        | Dolby Digital Plus encoding                  |
| `encode ddp-bluray` | Dolby Digital Plus BluRay encoding           |
| `encode atmos`      | Dolby Atmos encoding                         |
| `encode preset`     | Preset-based encoding (format auto-detected) |
| `find`              | File discovery with glob patterns            |
| `info`              | Audio stream analysis and metadata display   |
| `config`            | Configuration file management                |
| `temp`              | Temporary folder management                  |

## 🎵 Audio Encoding

### Dolby Digital (DD) Encoding

Perfect for legacy compatibility and smaller file sizes.

```bash
# Basic DD encoding with smart defaults
deezy encode dd input.mkv

# Specify channel layout and bitrate
deezy encode dd --channels 6 --bitrate 448 input.mkv

# Custom output path and keep temporary files
deezy encode dd --output "output.ac3" --keep-temp input.mkv
```

**Channel Options:**

- `0` (AUTO), `1` (MONO), `2` (STEREO), `6` (5.1 SURROUND)

**Common Options:**

- `--bitrate`: Bitrate in Kbps (uses smart defaults if not specified)
- `--drc-line-mode`: Dynamic range compression (film_standard, film_light, music_standard, music_light, speech)
- `--stereo-down-mix`: Stereo downmix method (auto, loro, ltrt, dpl2)

**Advanced DD Options:**

- `--track-index`: Select audio track (default: 0)
- `--delay`: Audio delay adjustment (--delay=-10ms or --delay=10s)
- `--custom-dialnorm`: Custom dialnorm value (0 to disable)
- `--metering-mode`: Loudness metering (1770_1, 1770_2, 1770_3, leqa)
- `--no-dialogue-intelligence`: Disable dialogue intelligence
- `--speech-threshold`: Speech detection threshold (0-100)

### Dolby Digital Plus (DDP) Encoding

Enhanced quality with higher bitrates and advanced features.

```bash
# Basic DDP encoding with smart defaults
deezy encode ddp input.mkv

# High-quality 5.1 encoding
deezy encode ddp --channels 6 --bitrate 448 input.mkv

# 7.1 surround encoding
deezy encode ddp --channels 8 --bitrate 768 input.mkv
```

**Channel Options:**

- `0` (AUTO), `1` (MONO), `2` (STEREO), `6` (5.1 SURROUND), `8` (7.1 SURROUNDEX)

**Key Features:**

- **📈 Higher Bitrates**: Support for bitrates up to 1024+ Kbps
- **🎚️ Advanced Processing**: Enhanced audio processing options
- **� Smart Defaults**: Automatic bitrate selection based on channel layout

### Dolby Digital Plus BluRay (DDP-BluRay) Encoding

Specialized DDP encoding optimized for BluRay disc mastering.

```bash
# BluRay DDP encoding (defaults to 7.1)
deezy encode ddp-bluray input.mkv

# Custom bitrate for BluRay
deezy encode ddp-bluray --bitrate 1536 input.mkv
```

### Dolby Atmos Encoding

Professional Atmos encoding for immersive audio.

```bash
# Atmos encoding with streaming mode (default)
deezy encode atmos input.mkv

# BluRay Atmos encoding
deezy encode atmos --atmos-mode bluray --bitrate 768 input.mkv
```

**Atmos Options:**

- `--atmos-mode`: `streaming` or `bluray`
- `--thd-warp-mode`: Warp mode for TrueHD processing (`normal`)
- `--no-bed-conform`: Disable bed conformance

Use `deezy encode --help` or `deezy encode [format] --help` to see all available options for each encoding format.

## 🔍 File Management & Analysis

### Find Files

Powerful file discovery with glob pattern support.

```bash
# Find all MKV files in current directory
deezy find "*.mkv"

# Find all video files recursively
deezy find "**/*.{mkv,mp4,avi}"

# Show only filenames (not full paths)
deezy find -n "**/*.mkv"
```

Use `deezy find --help` for additional options.

### Audio Stream Analysis

Get detailed information about audio tracks before encoding.

```bash
# Analyze audio streams
deezy info input.mkv

# Analyze multiple files
deezy info *.mkv
```

Use `deezy info --help` for additional options.

The `Track ... : 0` corresponds to the `-t / --track-index` argument when selecting your track to encode.

### Configuration Management

Manage DeeZy's configuration system for streamlined workflows.

```bash
# Generate default configuration file
deezy config generate

# Show current configuration status
deezy config info

# Generate config with overwrite protection disabled
deezy config generate --overwrite
```

Use `deezy config --help` for additional options and subcommands.

### Temporary Folder Management

DeeZy creates temporary folders during encoding operations. These folders contain intermediate files like WAV audio and DEE configuration files. The temp management system provides tools to monitor and clean up these folders.

#### Temp Folder Structure

DeeZy organizes temporary files in a clean structure:

```
%TEMP%/deezy/           # Parent folder for all DeeZy operations
├── job_abc123/         # Individual job folders (no deezy_ prefix)
├── job_def456/         # Each job gets a unique folder
└── job_ghi789/         # Clean, organized structure
```

This approach keeps your system temp directory clean and makes it easy to manage DeeZy-related temporary files.

#### Temp Management Commands

```bash
# Show temp folder information
deezy temp info

# Clean old temp folders (24 hours by default)
deezy temp clean

# Clean folders older than specific age
deezy temp clean --max-age 1  # 1 hour

# Preview what would be cleaned (dry run)
deezy temp clean --dry-run

# Clean very old folders with dry run
deezy temp clean --max-age 168 --dry-run  # 1 week
```

**Temp Info Output:**

```
DeeZy temp folder: C:\Users\Username\AppData\Local\Temp\deezy
Job folders: 3
Total size: 2.1 MB
```

**Temp Clean Features:**

- **Safe by default**: 24-hour age limit prevents accidental deletion of active jobs
- **Dry run mode**: Preview what would be deleted without making changes
- **Flexible age control**: Specify custom age thresholds in hours
- **Size reporting**: Shows how much space will be freed
- **Error handling**: Gracefully handles permission issues and locked files

**When to Use Temp Management:**

- **After batch processing**: Clean up after encoding many files
- **Storage maintenance**: Free up disk space from old encoding jobs
- **Debugging cleanup**: Remove temp files after troubleshooting
- **Scheduled maintenance**: Regular cleanup of accumulated temp files

Use `deezy temp --help` for additional options and subcommands.

## 🎯 Input Types & Patterns

DeeZy supports flexible input handling for batch processing:

### Multiple Files

```bash
# Process multiple files with same settings
deezy encode ddp input1.mkv input2.mp4 input3.avi

# Files with spaces (use quotes)
deezy encode ddp "Movie Name (2023).mkv" "Another Movie.mkv"
```

### Glob Patterns

```bash
# All MKV files in directory
deezy encode ddp "directory/*.mkv"

# Recursive search for all video files
deezy encode ddp "movies/**/*.{mkv,mp4,avi}"

# Pattern matching
deezy encode ddp "*TrueHD*.mkv"
```

## 🛠️ Advanced Configuration

### Configuration-Driven Workflows

The configuration system enables powerful workflow optimizations:

```bash
# Set up your environment once
deezy config generate
# Edit config file with your tool paths, defaults, and presets

# Now use clean commands for different scenarios:

# Use smart defaults - automatically applies format-specific settings
deezy encode ddp input.mkv

# Use presets for consistent workflows
deezy encode preset --name streaming_ddp input.mkv
deezy encode preset --name bluray_atmos input.mkv

# Override specific settings when needed
deezy encode preset --name streaming_ddp --bitrate 1024 input.mkv

# Batch processing with consistent preset settings
deezy encode preset --name streaming_ddp "season01/**/*.mkv"
```

**Configuration Benefits:**

- **Eliminate repetitive arguments** - Set tool paths and defaults once
- **Project consistency** - Same encoding settings across files
- **Environment portability** - Share config files between machines
- **Workflow optimization** - Different configs for different use cases

### Bitrate Guidelines

| Format     | Layout    | Default Bitrate | Accepted Range | Use Case              |
| ---------- | --------- | --------------- | -------------- | --------------------- |
| DD         | MONO      | 192 kbps        | 96-640 kbps    | Mono content          |
| DD         | Stereo    | 224 kbps        | 96-640 kbps    | Stereo content        |
| DD         | 5.1       | 448 kbps        | 224-640 kbps   | Legacy compatibility  |
| DDP        | MONO      | 64 kbps         | 32-1024 kbps   | Mono streaming        |
| DDP        | Stereo    | 128 kbps        | 96-1024 kbps   | Stereo streaming      |
| DDP        | 5.1       | 192 kbps        | 192-1024 kbps  | Streaming services    |
| DDP        | 7.1       | 384 kbps        | 384-1024 kbps  | High-quality releases |
| DDP BluRay | 7.1       | 384 kbps        | 768-1664 kbps  | BluRay mastering      |
| Atmos      | Streaming | 448 kbps        | 384-768 kbps   | Streaming Atmos       |
| Atmos      | BluRay    | 448 kbps        | 1152-1664 kbps | BluRay Atmos          |

_Note: All defaults are configurable via the configuration system_

### Dynamic Range Compression (DRC)

Available for both line mode and RF mode:

- **film_standard**: Heavy compression for noisy environments
- **film_light**: Light compression maintaining dynamics (default)
- **music_standard**: Balanced for music content
- **music_light**: Minimal compression for audiophile listening
- **speech**: Optimized for dialogue clarity

```bash
# Set DRC for line and RF modes
deezy encode ddp --drc-line-mode film_light --drc-rf-mode music_light input.mkv
```

### Temporary File Management

Use `-k/--keep-temp` to retain intermediate files for debugging or manual processing. Temporary files include:

- **WAV files**: Decoded audio streams
- **XML files**: DEE job configurations
- **LOG files**: Encoding process details

DeeZy automatically organizes temporary files under a dedicated `deezy` folder in your system temp directory. Use the temp management commands to monitor and clean up these files:

```bash
# Monitor temp folder usage
deezy temp info

# Clean up after batch processing
deezy temp clean --max-age 1

# Debug with temp files and clean up afterward
deezy encode ddp --keep-temp input.mkv
deezy temp clean --dry-run  # Check what will be cleaned
deezy temp clean            # Clean up when ready
```

## 📚 Examples & Workflows

### Movie Encoding Workflow

```bash
# 1. Set up configuration once
deezy config generate

# 2. Analyze the source
deezy info "Movie.Name.2023.UHD.mkv"

# 3. Encode with preset for consistency
deezy encode preset --name bluray_atmos "Movie.Name.2023.UHD.mkv"

# 4. Or customize settings manually
deezy encode atmos --atmos-mode bluray --bitrate 768 "Movie.Name.2023.UHD.mkv"

# 5. Verify output
deezy info "Movie.Name.2023.UHD.DDP.Atmos.ec3"
```

### Batch TV Series Processing

```bash
# Find all episodes
deezy find "TV.Series.S01**/*.mkv"

# Encode entire season with streaming preset
deezy encode preset --name streaming_ddp "TV.Series.S01**/*.mkv"

# Or with custom settings for dialogue-heavy content
deezy encode ddp --channels 6 --bitrate 448 --drc-line-mode speech "TV.Series.S01**/*.mkv"

# Clean up temp files after batch processing
deezy temp info         # Check temp folder status
deezy temp clean        # Clean up old temp files
```

### Quality Control

```bash
# Keep temporary files for analysis
deezy encode ddp --keep-temp input.mkv

# Use custom temp directory
deezy encode ddp --temp-dir "C:\debug\" input.mkv
```

## 🚨 Troubleshooting

### Common Issues

**"TrueHD decoder not found"**

- Ensure TrueHD decoder is installed and in PATH
- Only required for Atmos encoding from TrueHD sources

**"Invalid bitrate for channel layout"**

- Check the bitrate guidelines table for appropriate values
- DeeZy will automatically adjust to the nearest valid bitrate if possible

**"FFmpeg not found"**

- Install FFmpeg and add to system PATH
- Required for all audio processing operations

**"DEE executable not found"**

- Install Dolby Encoding Engine
- Set DEE path with `--dee` parameter or in config file

**"Configuration file issues"**

- Use `deezy config info` to check config status
- Regenerate config with `deezy config generate --overwrite`
- Ensure TOML syntax is valid in manual edits

**"Disk space issues"**

- Check temp folder usage with `deezy temp info`
- Clean old temp files with `deezy temp clean`
- Use `--temp-dir` to specify alternative temp location
- Monitor temp folder growth during batch processing

**"Temp folder permission errors"**

- Ensure write permissions to system temp directory
- Use `--temp-dir` to specify accessible location
- Check `deezy temp info` for temp folder location

### Debug Mode

```bash
# Enable verbose logging
deezy --log-level debug encode ddp input.mkv

# Write logs to file and keep temporary files
deezy --log-to-file encode ddp --keep-temp --temp-dir "C:\debug\" input.mkv

# Use custom config for troubleshooting
deezy --config debug-config.toml encode ddp input.mkv
```

## 🔗 Resources

- **📖 Dolby Encoding Engine Documentation**: `docs/dolbyencodingengineusersguide.pdf`
- **🔧 Channel Layout Reference**: `deezy/enums/`
- **🎵 Audio Filter Documentation**: DEE user guide for advanced filtering

## 📄 License

This project is licensed under the terms specified in the LICENSE file.

---
