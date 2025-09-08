# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Logging that will show substantially more information when used with DEBUG.
- Program wide configurable logger (defaults to INFO).
- CLI args:
  - General:
    - `--log-level`: Sets the log level (defaults to INFO).
    - `--log-to-file`: Write log to file (defaults to input path with suffix of .log).
    - `--no-progress-bars`: Disables progress bars on level INFO (disabled for DEBUG or higher).
    - `--drc-line-mode`: Dynamic range compression settings.
    - `--drc-rf-mode`: Dynamic range compression settings.
    - `--custom-dialnorm`: Custom dialnorm (0 disables custom dialnorm).
    - `--no-dialogue-intelligence`: Dialogue Intelligence enabled. Option ignored for 1770-1 or LeqA metering mode.
    - `--speech-threshold`: If the percentage of speech is higher than the threshold, the encoder uses speech gating to set the dialnorm value. (Otherwise, the encoder uses level gating).
    - `--no-low-pass-filter`: Disables low pass filter.
    - `--no-surround-3db`: Disables surround 3db attenuation.
    - `--no-surround-90-deg-phase-shift`: Disables surround 90 degree phase shift.
    - `--lt-rt-center`: Lt/Rt center downmix level.
    - `--lt-rt-surround`: Lt/Rt surround downmix level.
    - `--lo-ro-center`: Lo/Ro center downmix level.
    - `--lo-ro-surround`: Lo/Ro surround downmix level.
  - DD:
    - `--metering-mode`: Loudness measuring mode according to one of the broadcast standards.
  - DDP-BluRay:
    - `ddp-bluray`: Added a new encoder mode to allow higher bitrates for channel 7.1 layouts.

### Fixed

- Steps in progress output could be incorrect.
- Issues where progress sometimes wasn't reported correctly for very tiny file sizes.

### Changed

- Help portions of the CLI are now cleaner, using user friendly strings instead of raw enums.
- Improved automatic bitrate selection when the user choses an invalid bitrate, if 2 valid bitrates are returned it now automatically chooses the next highest quality.
- Re-wrote DD encoder module.
- DEE is no longer fed XML, it's handled via JSON.
- DRC default is now FILM_LIGHT.
- Updated numerous help strings for CLI args to be more descriptive/nicer.
- Progress Changes:
  - For very tiny files once the progress returns 0 where the progress could sometimes only be calculated to 99%, progress is now updated to 100%.
  - Added progress bars for each task/step _(this can be toggled via `--no-progress-bars` or by setting `--log-level` to DEBUG)_ .
  - Unified all logic for progress, easier to maintain and update if needed later.

### Removed

- **All shorthand arguments** (-c, etc.).
- Removed `--normalize`.

## [1.0.0] - 2025-09-05

### Added

- **Dolby Atmos Support**: Full support for Atmos encoding
  - TrueHD Atmos decoder integration
  - Atmos-specific CLI arguments (`--atmos`, `--no-bed-conform`)
  - Support for Atmos channel layouts (5.1.2, 5.1.4, 7.1.2, 7.1.4)
  - Automatic fallback to regular DDP if no Atmos content detected
- **Smart Dependencies**: Conditional TrueHD decoder requirement
  - Only requires TrueHD decoder when actually encoding Atmos content
  - Graceful dependency detection and error handling
- **Enhanced Channel Support**: Extended channel layout options
  - Added Atmos channel configurations
  - Improved channel auto-detection
- **Configuration System**: Complete TOML-based configuration management
  - `deezy config generate` - Generate default configuration files
  - `deezy config info` - Display configuration status and active settings
  - `deezy config generate --overwrite` - Replace existing configuration
  - Automatic config detection in multiple locations (portable and user directories)
  - Dependency path configuration (FFmpeg, DEE, TrueHD)
  - Encoding defaults per format (DD/DDP)
  - Global preferences (progress mode, temp directory, etc.)
  - User-defined preset support with full CLI integration
  - `--preset` CLI flag for using predefined encoding profiles
  - Preset validation and error handling with helpful error messages
  - Priority system: CLI args > Preset values > Config file > Built-in defaults
- Configuration schema validation with proper error handling
- Configuration integration with CLI argument parsing
- Smart dependency detection using config values as fallbacks

### Changed

- Enhanced README with comprehensive configuration system documentation
  - Added preset system usage examples and workflows
  - Updated Quick Start section with preset examples
  - Comprehensive configuration setup guide
  - Updated encoding workflow examples
- Updated CLI help to include configuration commands
- Improved dependency resolution to use configuration paths when CLI paths not specified
- **DDP Encoder Improvements**: Complete class refactoring
  - Proper typing throughout DDP encoder class
  - Cleaned up encoder logic and error handling
  - Fixed numerous potential errors in encoding pipeline
- **MediaInfo Optimization**: Streamlined payload handling
  - Optimized MediaInfo payload processing
  - Improved metadata extraction efficiency
- **FFmpeg Optimizations**: Enhanced external process handling
  - Optimized FFmpeg calls for better performance
  - Improved audio processing pipeline
- **DEE Encoder Enhancements**: Refined Dolby Encoding Engine integration
  - Optimized calls to DEE encoder
  - Updated default speech threshold from 15 to 20
  - Updated default DRC to "Film Standard"

### Fixed

- TOML file generation now produces proper TOML format (using `tomlkit.dumps()`)
- Configuration command parsing no longer requires input files
- Proper scoping of dependency path variables in CLI integration
- **README Formatting**: Fixed markdown structure and nesting issues
  - Corrected malformed code blocks (````)
  - Fixed missing `</details>` closing tags
  - Properly nested collapsible sections
  - Balanced details/summary block structure
- **Temp Path Handling**: Resolved potential temp directory build issues
- **Edge Case Errors**: Fixed potential errors during DEE encoding
- **Process Reliability**: Improved error handling in encoding workflows
