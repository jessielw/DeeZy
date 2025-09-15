# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.4] - 2025-09-14

### Fixed

- Atmos streaming mode was missing 1024 bitrate selection.
- Atmos bluray mode was defaulting to 448, should have been 1280 (this would have been corrected automatically).

## [1.2.3] - 2025-09-14

### Added

- Will now read delay from file if it's not provided over CLI and the audio is not in a container with other streams (Video, audio, text, etc).

### Fixed

- In the generated config **dependency** `truehd` should be `truehdd`. This is fixed when you generate a new config, but you can manually modify it.
- Dependencies was not being pulled from the config if provided.

## [1.2.2] - 2025-09-12

### Fixed

- Progress reporting in debug mode could sometimes be in accurate between DEE measure -> encode phases.
- Progress was time instead of percentage in ffmpeg with no progress bars for non atmos jobs.

## [1.2.1] - 2025-09-11

### Added

- Automatic detection for tty terminals to disable rich progress bars when DeeZy is called as a subprocess.

### Fixed

- TrueHD files with off time codes could sometimes have a FFMPEG warning (that is harmless) that could cause issues with reporting progress.

### Changed

- DeeZy now only buffers one line for real time progress when called as a progress.

## [1.2.0] - 2025-09-10

### Added

- New CLI args to manage your the automatic temp directory.
- Now checks for valid arguments on presets and gives the user helpful error messages.
- For formats that don't have a duration available (THD, other raw elementary formats) there is now a loading circle for progress when processing with FFMPEG.
- DEE related errors will be displayed without deezy running in DEBUG mode. (You may still need to run in debug for edge cases).
- `deezy config generate` now generates a cleaner and more descriptive default template.
- Checks for required executable dependencies in the CLI before attempting to run any encoders.
- Some more arg parser help messages.

### Fixed

- Generated config had invalid pre defined presets.
- Numerous issues with config.
- Major bug where the user defined bitrate wouldn't be set on all 3 encoders since the re-work.
- Use case insensitive checks for DRC.
- DEE config `prepend_silence_duration` and `append_silence_duration` set to defaults.
- Fixed an issue opening files with no FPS/duration data (only effected elementary files).

### Changed

- Rebuilt config to be more maintainable with improved error handling.
- Preset arg has changed:
  - You now call preset as it's own "encoder" `deezy encode preset --name YOUR_PRESET_NAME`.
- DEE key `time_base` is now set to `file_position` instead of `embedded_timecode`.
- Automatic temp directory now stores all job files in a parent folder `deezy`.
- Set automatic bitrate selection when not supplied by the user to a **DEBUG** message instead of info.

### Removed

- Un-needed logging statement for channel defaults.

## [1.1.0] - 2025-09-09

### Added

- Config system that allows user defined defaults and presets.
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
    - `--metering-mode`: Loudness measuring mode according to one of the broadcast standards.
  - DDP-BluRay:
    - `ddp-bluray`: Added a new encoder mode to allow higher bitrates for channel 7.1 layouts.
  - Atmos:
    - `atmos`: Added a new encoder mode to separate Atmos from DDP.
    - `--atmos-mode`: Atmos encoding mode (streaming/bluray).
    - `thd-warp-mode`: Specify warp mode when not present in metadata (truehdd).
    - `--no-bed-conform`: Disables bed conformance for Atmos content (truehdd).

### Fixed

- Steps in progress output could be incorrect.
- Issues where progress sometimes wasn't reported correctly for very tiny file sizes.

### Changed

- Re-worked entire program essentially to utilize DEE and JSON, checking for accuracy, fixing numerous issues etc.
- Help portions of the CLI are now cleaner, using user friendly strings instead of raw enums.
- Improved automatic bitrate selection when the user choses an invalid bitrate, if 2 valid bitrates are returned it now automatically chooses the next highest quality.
- Re-wrote DD encoder module.
- Re-wrote DDP encoder module.
- DEE is no longer fed XML, it's handled via JSON.
- DRC default is now FILM_LIGHT.
- Updated numerous help strings for CLI args to be more descriptive/nicer.
- Progress Changes:
  - For very tiny files once the progress returns 0 where the progress could sometimes only be calculated to 99%, progress is now updated to 100%.
  - Added progress bars for each task/step _(this can be toggled via `--no-progress-bars` or by setting `--log-level` to DEBUG)_ .
  - Unified all logic for progress, easier to maintain and update if needed later.
- CLI help indent has been slightly increased.

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
