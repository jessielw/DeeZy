# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

-

### Fixed

- Steps in progress output could be incorrect.

### Changed

- 

### Removed

-

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
