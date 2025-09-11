# GitHub Actions CI/CD Workflows

This directory contains GitHub Actions workflows for automated testing, building, and releasing DeeZy.

## Workflows

### 🧪 `test.yml` - Continuous Testing

- **Triggers**: Push to main/master, Pull Requests
- **Purpose**: Run tests and linting across multiple Python versions and operating systems
- **Matrix**: Python 3.11, 3.12 on Ubuntu, macOS, Windows
- **Features**:
  - Runs `ruff` linting
  - Executes pytest with coverage
  - Uploads coverage to Codecov (Ubuntu + Python 3.11 only)

### 🚀 `release.yml` - Release Builds

- **Triggers**:
  - GitHub Release published
  - Manual workflow dispatch
- **Purpose**: Build cross-platform executables and attach to releases
- **Platforms**: Linux (x64), macOS (x64), Windows (x64)
- **Features**:
  - Builds PyInstaller executables for all platforms
  - Runs tests before building
  - Automatically attaches binaries to GitHub releases
  - Artifacts retained for 7 days

### 🔧 `build-test.yml` - Manual Build Testing

- **Triggers**: Manual workflow dispatch only
- **Purpose**: Test builds without creating a release
- **Features**:
  - Selective platform building (linux, macos, windows, or all)
  - Tests executable functionality (`--help` command)
  - Short-term artifacts (1 day retention)

## Usage

### Creating a Release

1. **Update Version** (using the helper script):

   ```bash
   # Check current version
   python version.py --current

   # Validate version consistency
   python version.py --validate

   # Set new version (updates pyproject.toml - single source of truth)
   python version.py --set "1.2.0"

   # Create and push git tag
   python version.py --tag --push
   ```

2. **Create GitHub Release**:

   - Go to GitHub → Releases → Create new release
   - Choose the tag you just created
   - Add release notes
   - Publish the release

3. **Automatic Build**: The `release.yml` workflow will automatically:
   - Build executables for Linux, macOS, and Windows
   - Run tests on all platforms
   - Attach the built binaries to your release

### Manual Testing

To test builds without creating a release:

1. Go to Actions → Build Test
2. Click "Run workflow"
3. Choose platforms: `all`, `linux`, `macos`, `windows`, or combinations like `linux,windows`
4. The workflow will build and test the selected platforms
5. Download artifacts to test locally

### Release Assets

When a release is created, the following ZIP archives are automatically generated:

- `deezy-linux-x64.zip` - Contains `deezy` Linux executable
- `deezy-macos-x64.zip` - Contains `deezy` macOS executable
- `deezy-windows-x64.exe.zip` - Contains `deezy.exe` Windows executable

Each ZIP file contains the executable with its proper name (`deezy` or `deezy.exe`), making it easy for users to extract and use directly.

## Requirements

- Python 3.11+ (specified in workflows)
- `uv` package manager (automatically installed)
- All dependencies defined in `pyproject.toml`

## Troubleshooting

### Build Failures

1. **Missing Dependencies**: Ensure `pyproject.toml` includes all required packages in `[project.optional-dependencies.build]`
2. **PyInstaller Issues**: Check the build logs for PyInstaller-specific errors
3. **Platform-Specific Issues**: Use the `build-test.yml` workflow to test individual platforms

### Release Issues

1. **Missing Binaries**: Check the release workflow logs to see if builds completed successfully
2. **Upload Failures**: Verify GitHub token permissions for release asset uploads
3. **Version Conflicts**: Ensure version in `pyproject.toml` matches the git tag

## Version Management

DeeZy uses **pyproject.toml as the single source of truth** for version information:

- **pyproject.toml**: Contains the authoritative version
- **deezy/utils/\_version.py**: Dynamically reads from pyproject.toml at runtime
- **version.py**: Helper script for updating versions and creating releases

This approach eliminates version synchronization issues between multiple files.

### Version Validation

```bash
# Ensure version consistency across files
python version.py --validate
```

## Security

- Uses `GITHUB_TOKEN` for release uploads (automatically provided by GitHub)
- No external secrets required
- All dependencies installed from official sources
