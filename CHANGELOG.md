# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Config:

  - Default bitrates setting for AC4.

- CLI:

  - `--parse-elementary-delay` - When input is an elementary (demuxed) stream, parse any delay in the filename and reset it to zero.
  - `--working-dir` - Set a centralized working directory for job files, logs, and batch-results. Overrides config default when provided.
  - `--batch-summary-output` - Path to write a JSON summary for a batch run. When provided, a single JSON file with per-file metadata (status, durations, log file, output path) is emitted.
  - `--batch-output-dir` - When supplied, encoders will place generated outputs into this directory unless the user explicitly supplied `--output` for a job. Useful for centralized batch storage.
  - `--overwrite` - Global flag to allow overwriting existing output files. When not set, the CLI will fast-fail/skips jobs whose target outputs already exist.
  - `--max-parallel` - Integer (default 1). Controls how many files are processed concurrently in batch mode.
  - `--max-logs` - Integer to retain a maximum number of log files in the working logs directory; older logs are trimmed automatically.
  - `--max-batch-results` - Integer to retain a maximum number of batch result JSON files in the working batch-results directory; older results are trimmed.

- Encoders / Internal:

  - Centralized atomic move helper in the DEE encoder base class to perform safe, fast output file placement. Uses an atomic replace when possible and falls back to a cross-filesystem-safe move when needed.
  - DRY refactor: replaced per-encoder unlink+move logic with the centralized helper across DD, DDP, Atmos and AC4 encoders. This unifies overwrite semantics and reduces duplicated code.
  - Automatic filename generation has been greatly improved:
    - Will check for common attributes via the mediainfo/input name and append that to the automatically generated file name.
    - Detects name, year, season, episode and adds them to the name when generating a new name.
  - Concurrency & phase limits:
    - New CLI flags: `--limit-ffmpeg`, `--limit-dee`, `--limit-truehdd` allow fine-tuning concurrency for each heavy phase.
    - If per-phase flags are not provided, each phase defaults to the value of `--max-parallel`.
    - Exception: the DEE phase defaults to a conservative fraction of `--max-parallel` (roughly half) to avoid saturating CPU/IO on slower machines; users can override with `--limit-dee`.
    - Values greater than `--max-parallel` are capped to `--max-parallel` and a warning is emitted at startup.
    - `--jitter-ms` flag: introduces a small randomized delay before heavy phases to reduce thundering-herd spikes in high-parallel runs.

- Per-source default bitrates (opt-in):

  - Added support for optional per-source default bitrate sections in the configuration file under `[default_source_bitrates.<codec>]` (for example `[default_source_bitrates.ddp]`).
  - Keys are `ch_1..ch_8` and are opt-in (the generated `deezy-conf.toml` contains commented example blocks). Encoders will use these values when no CLI/preset bitrate is provided. Encoders validate config values and will select the closest allowed bitrate if a configured value is not permitted. Precedence is: CLI > per-source config > format-level config > built-in defaults.

### Changed

- Config **Breaking Change**:
  - `[default_bitrates.ddp_bluray]` needs to be renamed to `[default_bitrates.ddp-bluray]` to match the codec properly. This will be automatic if you generate a new config, otherwise you should make this change manually if using the config.
  - Updated some of the default bitrates in the generated config.
- Parsing delay from filename:
  - When a file is in it's **elementary** format _(demuxed by itself)_ and there is a delay string we will parse it and zero it out if `--parse-elementary-delay` is used. This will effectively set the audio to 0ms delay during encoding as well as strip it from the filename.
    - If the user explicitly defines an output file name no logic will be ran on the output file (as to not change the users desired output name).
  - If `--parse-elementary-delay` is **not** used, delays will be handled like they was previously in containers and no logic will be ran against **elementary** files.
- Improved language detection for **elementary** formats.
- Updated default config.

### Fixed

- Codec channel/bitrate defaults from config was not being set.

### Removed

-

## [1.2.6] - 2025-09-17

### Changed

- Arg `--no-bed-conform` is changed to `--bed-conform` as it now defaults to **Off**.

### Fixed

- Hard coded default for **DolbyDigitalPlusBluRay** mode _(would have been corrected regardless)_.

## [1.2.5] - 2025-09-16

### Added

- Now captures **all** exceptions and logs them in **debug** mode.
- `--track-index`: _(where **N** is your typical track index)_
  - `a:N`
    - This is the same behavior as before.
  - `s:N`
    - Works identically to FFMPEG's `-map 0:N` command, it access the track based on the stream instead of audio.
  - Note, backwards compatibility is retained, you can still simply pass `--track-index N`.
- Added support for **AC4**:
  - New `encode ac4` command for next-generation Dolby AC-4 encoding
  - `--encoding-profile`: Support for IMS and IMS Music profiles
  - `--ims-legacy-presentation`: Backward compatibility presentation option
  - Multiple independent DRC settings for different playback scenarios:
    - `--ddp-drc`: DDP-compatible DRC settings
    - `--flat-panel-drc`: Flat panel TV speaker optimization
    - `--home-theatre-drc`: Home theater system optimization
    - `--portable-headphones-drc`: Portable device and headphone optimization
    - `--portable-speakers-drc`: Small speaker optimization
  - Automatic TrueHD Atmos metadata preservation in immersive stereo output
  - Requires minimum 6-channel (5.1) input or higher
  - Enhanced metering with full 1770-4 loudness standard support

### Changed

- Progress bars will now be the same width.
- Progress bar time elapsed has been replaced by a spinner.
- Added a new example preset `ac4_stereo` to the default config.

### Fixed

- Handle weird inputs with _multiple_ channel counts _(i.e. 8 / 6)_ and correctly determine the highest count.
- Issue where paths could break for MacOS.

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
