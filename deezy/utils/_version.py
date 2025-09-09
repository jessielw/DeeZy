from pathlib import Path

import tomlkit

# static information
program_name = "DeeZy"
developed_by = "jlw4049 and eSTeeM"


def get_version():
    """Get version from pyproject.toml."""
    try:
        # find pyproject.toml - look in current dir and parent dirs
        current_path = Path(__file__).parent
        for _ in range(5):  # search up to 5 levels up
            pyproject_path = current_path / "pyproject.toml"
            if pyproject_path.exists():
                with open(pyproject_path, "r", encoding="utf-8") as f:
                    data = tomlkit.load(f)
                project = data.get("project", {})
                version = project.get("version", "1.0.0-dev")
                return str(version)
            current_path = current_path.parent

        # fallback if pyproject.toml not found
        return "1.0.0-dev"
    except Exception:
        # fallback for any errors
        return "1.0.0-dev"


# dynamic version
__version__ = get_version()
