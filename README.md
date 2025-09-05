# DeeZy

A powerful, portable audio encoding tool built around the Dolby Encoding Engine (DEE) with support for Dolby Digital (DD), Dolby Digital Plus (DDP), and **Dolby Atmos** encoding.

## ✨ Key Features

- **🎵 Multiple Audio Formats**: Support for Dolby Digital (DD), Dolby Digital Plus (DDP), and Dolby Atmos
- **🔧 Portable**: No installation required - just download and run
- **⚙️ Smart Configuration**: TOML-based config system with dependency paths and encoding defaults
- **🎛️ Flexible Encoding**: Automatic channel detection, custom bitrates, and advanced audio processing
- **🌟 Atmos Support**: Full support for JOC (5.1.2/5.1.4) and BluRay Atmos (7.1.2/7.1.4) encoding
- **📁 Batch Processing**: Process multiple files or use glob patterns for bulk operations
- **🎚️ Advanced Controls**: Dynamic range compression, stereo downmix options, and audio normalization
- **⚡ Smart Dependencies**: Only requires TrueHD decoder when actually encoding Atmos content
- **🔍 Audio Analysis**: Built-in audio stream inspection and metadata display

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

DeeZy includes a powerful TOML-based configuration system that eliminates repetitive command-line arguments and allows you to set encoding defaults.

### Quick Configuration Setup

```bash
# Generate a default configuration file
deezy config generate

# Check configuration status
deezy config info

# Overwrite existing configuration
deezy config generate --overwrite
```

### Configuration File Structure

The configuration file supports:

- **Dependency paths** (FFmpeg, DEE, TrueHD)
- **Encoding defaults** per format (DD/DDP)
- **Global preferences** (temp directory, progress mode)
- **Custom presets** for common workflows

```toml
[dependencies]
# Paths to external tools (leave empty for auto-detection)
ffmpeg = "C:/tools/ffmpeg.exe"
dee = "C:/apps/dee/dee.exe"
truehdd = "C:/decoder/truehd.exe"

[defaults.ddp]
# Your preferred DDP encoding defaults
channels = "5.1"
bitrate = 768
drc = "FILM_LIGHT"
normalize = true

[presets]
# Custom encoding presets for different workflows
streaming = { format = "ddp", channels = "5.1", bitrate = 768, normalize = true }
bluray_atmos = { format = "ddp", channels = "ATMOS_7_1_4", bitrate = 1664, atmos = true }
quick_test = { format = "ddp", channels = "stereo", bitrate = 256 }
```

### Configuration Locations

DeeZy automatically searches for configuration files in:

1. **Portable**: `deezy-config.toml` beside the executable
2. **User directory**:
   - Windows: `%APPDATA%/DeeZy/config.toml`
   - Linux/macOS: `~/.config/deezy/config.toml`

### Priority System

Configuration values are applied in order of priority:
**CLI Arguments** > **Config File** > **Built-in Defaults**

### Multiple Workflows with Presets

The preset system is **fully implemented** and allows you to define multiple encoding profiles in a single config file:

```toml
[presets]
# Different workflows for your encoding needs
streaming = { format = "ddp", channels = "5.1", bitrate = 768, normalize = true }
bluray_atmos = { format = "ddp", channels = "ATMOS_7_1_4", bitrate = 1664, atmos = true }
quick_test = { format = "ddp", channels = "stereo", bitrate = 256 }
```

**Usage:**

```bash
# Use a preset for encoding
deezy encode ddp --preset streaming input.mkv

# Override preset settings as needed
deezy encode ddp --preset bluray_atmos --bitrate 1024 input.mkv

# List available presets
deezy config info
```

### Benefits

**Before Configuration:**

```bash
deezy encode ddp --ffmpeg "C:/tools/ffmpeg.exe" --dee "C:/apps/dee.exe" -c 5.1 -b 768 -drc FILM_LIGHT input.mkv
```

**After Configuration:**

```bash
deezy encode ddp input.mkv  # Uses your configured defaults!
```

## 🚀 Quick Start

```bash
# Encode to Dolby Digital Plus with automatic settings
deezy encode ddp input.mkv

# Encode to Dolby Atmos (5.1.4 layout)
deezy encode ddp --atmos -c 5.1.4 input.mkv

# Use a predefined preset
deezy encode ddp --preset streaming input.mkv

# Batch encode multiple files
deezy encode ddp *.mkv

# Get audio track information
deezy info input.mkv
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

| Option          | Description          |
| --------------- | -------------------- |
| `-v, --version` | Show program version |
| `-h, --help`    | Show help message    |

### Main Commands

| Command  | Description                  |
| -------- | ---------------------------- |
| `encode` | Audio encoding operations    |
| `find`   | File discovery with patterns |
| `info`   | Audio stream analysis        |
| `config` | Configuration management     |

## 🎵 Audio Encoding

### Dolby Digital (DD) Encoding

Perfect for legacy compatibility and smaller file sizes.

```bash
# Basic DD encoding with auto-detection
deezy encode dd input.mkv

# Specify channel layout and bitrate
deezy encode dd -c 5.1 -b 448 input.mkv

# Custom output path and keep temporary files
deezy encode dd -o "output.ac3" -k input.mkv
```

**Common Options:**

- `-c, --channels`: `AUTO`, `MONO`, `STEREO`, `SURROUND` (5.1)
- `-b, --bitrate`: Bitrate in Kbps (default: 448)
- `-s, --stereo-down-mix`: `STANDARD` or `DPLII` (Dolby Pro Logic II)
- `-drc`: Dynamic range compression profiles

<details>
<summary>📖 Full DD Usage</summary>

```
usage: DeeZy encode dd [-h] [--ffmpeg FFMPEG] [--truehdd TRUEHDD] [--dee DEE]
                       [-t TRACK_INDEX] [-b BITRATE] [-d DELAY] [-k]
                       [-p {STANDARD[0],DEBUG[1],SILENT[2]}] [-tmp TEMP_DIR]
                       [-o OUTPUT] [--preset PRESET]
                       [-s {STANDARD[0],DPLII[1]}]
                       [-c {AUTO[0],MONO[1],STEREO[2],SURROUND[6]}]
                       [-drc {FILM_STANDARD[0],FILM_LIGHT[1],MUSIC_STANDARD[2],MUSIC_LIGHT[3],SPEECH[4]}]
                       INPUT [INPUT ...]

positional arguments:
  INPUT
   Input file paths or directories

options:
  -h, --help
   show this help message and exit
  --ffmpeg, FFMPEG
   Path to FFMPEG executable.
  --truehdd, TRUEHDD
   Path to Truehdd executable.
  --dee, DEE
   Path to DEE (Dolby Encoding Engine) executable.
  -t, --track-index, TRACK_INDEX
   The index of the audio track to use.
  -b, --bitrate, BITRATE
   The bitrate in Kbps.
  -d, --delay, DELAY
   The delay in milliseconds or seconds. Note '-d=' is required! (-d=-10ms / -d=10s).
  -k, --keep-temp
   Keeps the temp files after finishing (usually a wav and an xml for DEE).
  -p, --progress-mode, {STANDARD[0],DEBUG[1],SILENT[2]}
   Sets progress output mode verbosity.
  -tmp, --temp-dir, TEMP_DIR
   Path to store temporary files to. If not specified this will automatically happen in the temp dir of the os.
  -o, --output, OUTPUT
   The output file path. If not specified we will attempt to automatically add Delay/Language string to output file name.
  --preset, PRESET
   Use a predefined configuration preset from config file.
  -s, --stereo-down-mix, {STANDARD[0],DPLII[1]}
   Down mix method for stereo.
  -c, --channels, {AUTO[0],MONO[1],STEREO[2],SURROUND[6]}
   The number of channels.
  -drc, --dynamic-range-compression, {FILM_STANDARD[0],FILM_LIGHT[1],MUSIC_STANDARD[2],MUSIC_LIGHT[3],SPEECH[4]}
   Dynamic range compression settings.
```

</details>

### Dolby Digital Plus (DDP) Encoding

Enhanced quality with support for higher bitrates and **Dolby Atmos**.

```bash
# Basic DDP encoding
deezy encode ddp input.mkv

# High-quality 5.1 encoding with normalization
deezy encode ddp -c 5.1 -b 768 --normalize input.mkv

# Dolby Atmos encoding (JOC - 5.1.4)
deezy encode ddp --atmos -c 5.1.4 -b 768 input.mkv

# Dolby Atmos encoding (BluRay - 7.1.4)
deezy encode ddp --atmos -c 7.1.4 -b 1536 input.mkv
```

**Key Features:**

- **🌟 Atmos Support**: Automatic detection and encoding of Atmos content
- **📈 Higher Bitrates**: Support for up to 1664 Kbps (BluRay Atmos)
- **🎚️ Audio Normalization**: Built-in loudness normalization
- **🔄 Smart Fallbacks**: Automatically falls back to regular DDP if no Atmos detected

**Channel Options:**

- Standard: `AUTO`, `MONO`, `STEREO`, `SURROUND` (5.1), `SURROUNDEX` (7.1)
- Atmos: `ATMOS_5_1_2`, `ATMOS_5_1_4`, `ATMOS_7_1_2`, `ATMOS_7_1_4`

<details>
<summary>📖 Full DDP Usage</summary>

```
usage: DeeZy encode ddp [-h] [--ffmpeg FFMPEG] [--truehdd TRUEHDD] [--dee DEE]
                        [-t TRACK_INDEX] [-b BITRATE] [-d DELAY] [-k]
                        [-p {STANDARD[0],DEBUG[1],SILENT[2]}] [-tmp TEMP_DIR]
                        [-o OUTPUT] [--preset PRESET]
                        [-s {STANDARD[0],DPLII[1]}]
                        [-c {AUTO[0],MONO[1],STEREO[2],SURROUND[6],SURROUNDEX[8],ATMOS_5_1_2[512],ATMOS_5_1_4[514],ATMOS_7_1_2[712],ATMOS_7_1_4[714]}]
                        [-n] [--atmos] [--no-bed-conform]
                        [-drc {FILM_STANDARD[0],FILM_LIGHT[1],MUSIC_STANDARD[2],MUSIC_LIGHT[3],SPEECH[4]}]
                        INPUT [INPUT ...]

positional arguments:
  INPUT
   Input file paths or directories

options:
  -h, --help
   show this help message and exit
  --ffmpeg, FFMPEG
   Path to FFMPEG executable.
  --truehdd, TRUEHDD
   Path to Truehdd executable.
  --dee, DEE
   Path to DEE (Dolby Encoding Engine) executable.
  -t, --track-index, TRACK_INDEX
   The index of the audio track to use.
  -b, --bitrate, BITRATE
   The bitrate in Kbps.
  -d, --delay, DELAY
   The delay in milliseconds or seconds. Note '-d=' is required! (-d=-10ms / -d=10s).
  -k, --keep-temp
   Keeps the temp files after finishing (usually a wav and an xml for DEE).
  -p, --progress-mode, {STANDARD[0],DEBUG[1],SILENT[2]}
   Sets progress output mode verbosity.
  -tmp, --temp-dir, TEMP_DIR
   Path to store temporary files to. If not specified this will automatically happen in the temp dir of the os.
  -o, --output, OUTPUT
   The output file path. If not specified we will attempt to automatically add Delay/Language string to output file name.
  --preset, PRESET
   Use a predefined configuration preset from config file.
  -s, --stereo-down-mix, {STANDARD[0],DPLII[1]}
   Down mix method for stereo.
  -c, --channels, {AUTO[0],MONO[1],STEREO[2],SURROUND[6],SURROUNDEX[8],ATMOS_5_1_2[512],ATMOS_5_1_4[514],ATMOS_7_1_2[712],ATMOS_7_1_4[714]}
   The number of channels.
  -n, --normalize
   Normalize audio for DDP (ignored for DDP channels above 6).
  --atmos
   Enable Atmos encoding mode for TrueHD input files with Atmos content (automatically falls back to DDP if no Atmos is detected).
  --no-bed-conform
   Disable bed conform for Atmos
  -drc, --dynamic-range-compression, {FILM_STANDARD[0],FILM_LIGHT[1],MUSIC_STANDARD[2],MUSIC_LIGHT[3],SPEECH[4]}
   Dynamic range compression settings.
```

</details>

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

<details>
<summary>📖 Full Find Usage</summary>

```
usage: DeeZy find [-h] [-n] INPUT [INPUT ...]

positional arguments:
  INPUT       Input file paths or directories

  -h, --help  show this help message and exit
  -n, --name  Only display names instead of full paths.
```

**Example:**

```bash
deezy find "Path\*.*"
# Output: Path\Men.in.Black.3.2012.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX.mkv
```

</details>

### Audio Stream Analysis

Get detailed information about audio tracks before encoding.

```bash
# Analyze audio streams
deezy info input.mkv

# Analyze multiple files
deezy info *.mkv
```

<details>
<summary>📖 Full Info Usage</summary>

```
usage: DeeZy info [-h] INPUT [INPUT ...]

positional arguments:
  INPUT       Input file paths or directories

options:
  -h, --help  show this help message and exit
```

Example:

```
deezy info "Path\Avatar.The.Last.Airbender.S01E01.The.Boy.in.the.Iceberg.mkv"
File: Avatar.The.Last.Airbender.S01E01.The.Boy.in.the.Iceberg.mkv
Audio tracks: [0]
------------------------------------------------------------------------------------------
Track               : 0
Codec               : FLAC - (flac)
Channels            : 2.0 - L R
Bit rate mode       : VBR / Variable
Bit rate            : 760 kb/s
Sampling Rate       : 48.0 kHz
Duration            : 23 min 40 s
Language            : English
Title               : FLAC 2.0
Stream size         : 128.7 MiB
Bit Depth           : 24 bits
Compression         : Lossless
Default             : Yes
Forced              : No
------------------------------------------------------------------------------------------
```

`Track ... : 0` corresponds to the `-t / --track-index` arg when selecting your track to encode with dd/ddp

</details>

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

<details>
<summary>📖 Full Config Usage</summary>

```
usage: DeeZy config [-h] {generate,info} ...

positional arguments:
  {generate,info}
    generate       Generate configuration file
    info           Show configuration information

options:
  -h, --help       show this help message and exit
```

#### Generate Command

```
usage: DeeZy config generate [-h] [-o OUTPUT] [--overwrite] [--from-args]

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        Output path for config file (default: auto-detect)
  --overwrite           Overwrite existing config file
  --from-args           Generate config from current CLI arguments (use with encode command)
```

#### Info Command

```
usage: DeeZy config info [-h] [--path PATH]

options:
  -h, --help       show this help message and exit
  --path PATH      Show specific config file path
```

**Example Output:**

```bash
# No config file
deezy config info
# Output: No configuration file found. Using built-in defaults.
#         Default config location: C:\Users\...\AppData\Roaming\DeeZy\config.toml

# With active config
deezy config info
# Output: Active config file: C:\Users\...\AppData\Roaming\DeeZy\config.toml
#         Presets available: streaming, bluray_atmos
```

</details>

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
# Edit config file with your tool paths and preferred settings

# Now use clean commands for different scenarios:

# Streaming workflow - uses config defaults
deezy encode ddp input.mkv

# Override specific settings when needed
deezy encode ddp -b 1024 -c 7.1 input.mkv

# Atmos workflow - automatically detects need for TrueHD
deezy encode ddp --atmos -c 7.1.4 input.truehd

# Batch processing with consistent settings
deezy encode ddp "season01/**/*.mkv"
```

**Configuration Benefits:**

- **Eliminate repetitive arguments** - Set tool paths and defaults once
- **Project consistency** - Same encoding settings across files
- **Environment portability** - Share config files between machines
- **Workflow optimization** - Different configs for different use cases

### Bitrate Guidelines

| Format    | Layout      | Recommended Bitrate | Use Case              |
| --------- | ----------- | ------------------- | --------------------- |
| DD        | 5.1         | 448-640 kbps        | Legacy compatibility  |
| DDP       | 5.1         | 640-768 kbps        | Streaming services    |
| DDP       | 7.1         | 768-1024 kbps       | High-quality releases |
| DDP Atmos | 5.1.2/5.1.4 | 768-1024 kbps       | JOC streaming         |
| DDP Atmos | 7.1.2/7.1.4 | 1152-1664 kbps      | BluRay mastering      |

### Dynamic Range Compression

- **FILM_STANDARD**: Heavy compression for noisy environments
- **FILM_LIGHT**: Light compression maintaining dynamics
- **MUSIC_STANDARD**: Balanced for music content
- **MUSIC_LIGHT**: Minimal compression for audiophile listening
- **SPEECH**: Optimized for dialogue clarity

### Temporary File Management

Use `-k/--keep-temp` to retain intermediate files for debugging or manual processing. Temporary files include:

- **WAV files**: Decoded audio streams
- **XML files**: DEE job configurations
- **LOG files**: Encoding process details

## 📚 Examples & Workflows

### Movie Encoding Workflow

```bash
# 1. Analyze the source
deezy info "Movie.Name.2023.UHD.mkv"

# 2. Encode with optimal settings using preset
deezy encode ddp --preset bluray_atmos "Movie.Name.2023.UHD.mkv"

# 3. Or customize settings manually
deezy encode ddp --atmos -c 7.1.4 -b 1536 -drc FILM_LIGHT "Movie.Name.2023.UHD.mkv"

# 4. Verify output
deezy info "Movie.Name.2023.UHD.DDP.Atmos.ec3"
```

### Batch TV Series Processing

```bash
# Find all episodes
deezy find "TV.Series.S01**/*.mkv"

# Encode entire season with streaming preset
deezy encode ddp --preset streaming "TV.Series.S01**/*.mkv"

# Or with custom settings
deezy encode ddp -c 5.1 -b 640 -drc SPEECH "TV.Series.S01**/*.mkv"
```

### Quality Control

```bash
# Test encoding settings without processing
deezy encode ddp -c 7.1.4 -b 1536 --print-only input.mkv

# Keep temporary files for analysis
deezy encode ddp -k input.mkv
```

## 🚨 Troubleshooting

### Common Issues

**"TrueHD decoder not found"**

- Ensure TrueHD decoder is installed and in PATH
- Only required for Atmos encoding from TrueHD sources

**"Invalid bitrate for channel layout"**

- 7.1.4 Atmos requires minimum 1152 kbps
- 5.1.2/5.1.4 Atmos requires minimum 768 kbps

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

### Debug Mode

```bash
# Enable verbose output
deezy encode ddp -p DEBUG input.mkv

# Keep all temporary files
deezy encode ddp -k -tmp "C:\debug\" input.mkv
```

## 🔗 Resources

- **📖 Dolby Encoding Engine Documentation**: `docs/dolbyencodingengineusersguide.pdf`
- **💡 Example Projects**: `example_project_using_thd/`
- **🔧 Channel Layout Reference**: `deezy/enums/`
- **🎵 Audio Filter Documentation**: DEE user guide for advanced filtering

## 📄 License

This project is licensed under the terms specified in the LICENSE file.

---
