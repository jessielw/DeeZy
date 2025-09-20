#!/usr/bin/env python3
"""
Version management script for DeeZy releases.
Updates version in pyproject.toml and creates git tags.
This maintains pyproject.toml as the single source of truth for version info.
"""

import argparse
from pathlib import Path
import re
import subprocess
import sys


def get_current_version():
    """Get current version from pyproject.toml."""
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        raise FileNotFoundError("pyproject.toml not found")

    content = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'version = "([^"]+)"', content)
    if not match:
        raise ValueError("Version not found in pyproject.toml")

    return match.group(1)


def validate_version_consistency():
    """Validate that the dynamic version loading works correctly."""
    try:
        # get version from pyproject.toml
        toml_version = get_current_version()
        sys.path.insert(0, str(Path.cwd()))
        from deezy.utils._version import __version__

        if toml_version != __version__:
            print("⚠️  WARNING: Version mismatch!")
            print(f"   pyproject.toml: {toml_version}")
            print(f"   _version.py:    {__version__}")
            return False
        else:
            print(f"✅ Version consistency verified: {toml_version}")
            return True

    except Exception as e:
        print(f"❌ Error validating version consistency: {e}")
        return False


def update_version(new_version):
    """Update version in pyproject.toml."""
    subprocess.run(("uv", "version", new_version))


def create_git_tag(version, push=False):
    """Create and optionally push git tag."""
    tag_name = f"v{version}"

    # create tag
    result = subprocess.run(
        ["git", "tag", "-a", tag_name, "-m", f"Release {tag_name}"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"Failed to create tag: {result.stderr}")
        return False

    print(f"Created git tag: {tag_name}")

    if push:
        # push tag
        result = subprocess.run(
            ["git", "push", "origin", tag_name], capture_output=True, text=True
        )

        if result.returncode != 0:
            print(f"Failed to push tag: {result.stderr}")
            return False

        print(f"Pushed git tag: {tag_name}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Manage DeeZy versions and releases")
    parser.add_argument("--current", action="store_true", help="Show current version")
    parser.add_argument("--set", metavar="VERSION", help="Set new version")
    parser.add_argument(
        "--tag", action="store_true", help="Create git tag for current version"
    )
    parser.add_argument("--push", action="store_true", help="Push git tag to origin")
    parser.add_argument(
        "--validate", action="store_true", help="Validate version consistency"
    )

    args = parser.parse_args()

    if args.current:
        try:
            version = get_current_version()
            print(f"Current version: {version}")
        except Exception as e:
            print(f"Error: {e}")
            return 1

    if args.validate:
        if not validate_version_consistency():
            return 1

    if args.set:
        try:
            update_version(args.set)
        except Exception as e:
            print(f"Error updating version: {e}")
            return 1

    if args.tag:
        try:
            version = get_current_version()
            success = create_git_tag(version, args.push)
            if not success:
                return 1
        except Exception as e:
            print(f"Error creating tag: {e}")
            return 1

    return 0


if __name__ == "__main__":
    exit(main())
