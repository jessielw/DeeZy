import os
from pathlib import Path
import re
from subprocess import run

from deezy.utils.dependencies import get_executable_extension


def get_site_packages() -> Path:
    output = run(
        ("uv", "pip", "show", "babelfish"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    get_location = re.search(r"Location: (.+)\n", output, flags=re.M)
    if not get_location:
        raise FileNotFoundError("Can not detect site packages")
    return Path(get_location.group(1))


def build_app():
    # define and create pyinstaller output path
    pyinstaller_folder = Path(Path(__file__).parent / "pyinstaller_build")
    pyinstaller_folder.mkdir(exist_ok=True)

    # define paths before changing directory
    deezy_script = Path(Path.cwd() / "deezy.py")
    icon_path = Path(Path.cwd() / "icon" / "icon.ico")

    # get guessit deps
    site_packages = get_site_packages()
    babel_fish = site_packages / "babelfish"
    guessit = site_packages / "guessit"

    # change directory so we output all of pyinstallers files in it's own folder
    os.chdir(pyinstaller_folder)

    # run pyinstaller onefile build
    build_job_onefile = run(
        [
            "uv",
            "run",
            "pyinstaller",
            "-n",
            "deezy",
            "--onefile",
            f"--add-data={babel_fish}:./babelfish",
            f"--add-data={guessit}:./guessit",
            f"--icon={str(icon_path)}",
            str(deezy_script),
        ]
    )

    # run pyinstaller onedir (bundle) build
    build_job_onedir = run(
        [
            "uv",
            "run",
            "pyinstaller",
            "-n",
            "deezy",
            "--distpath",
            "bundled_mode",
            "--contents-directory",
            "bundle",
            f"--add-data={babel_fish}:./babelfish",
            f"--add-data={guessit}:./guessit",
            f"--icon={str(icon_path)}",
            str(deezy_script),
        ]
    )

    exe_str = get_executable_extension()
    success_msgs = []

    # Check onefile build
    onefile_path = Path("dist") / f"deezy{exe_str}"
    if onefile_path.is_file() and str(build_job_onefile.returncode) == "0":
        success_msgs.append(f"Onefile build success! Path: {Path.cwd() / onefile_path}")
    else:
        success_msgs.append("Onefile build did not complete successfully")

    # Check onedir (bundle) build
    onedir_path = Path("bundled_mode") / "deezy" / f"deezy{exe_str}"
    if onedir_path.is_file() and str(build_job_onedir.returncode) == "0":
        success_msgs.append(f"Bundle build success! Path: {Path.cwd() / onedir_path}")
    else:
        success_msgs.append("Bundle build did not complete successfully")

    # change directory back to original directory
    os.chdir(deezy_script.parent)

    return "\n".join(success_msgs)


if __name__ == "__main__":
    build = build_app()
    print(build)
