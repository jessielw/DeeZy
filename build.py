from pathlib import Path
from subprocess import run
import os


def build_app():
    # define and create pyinstaller output path
    pyinstaller_folder = Path(Path(__file__).parent / "pyinstaller_build")
    pyinstaller_folder.mkdir(exist_ok=True)

    # define full path to deeaw.py before changing directory
    deeaw_script = Path(Path.cwd() / "deeaw.py")

    # change directory so we output all of pyinstallers files in it's own folder
    os.chdir(pyinstaller_folder)

    # run pyinstaller command
    command = ["pyinstaller.exe", "--onefile", str(deeaw_script)]
    run(command)

    # ensure output of exe
    success = "Did not complete succesfully"
    if Path(Path("dist") / "deeaw.exe").is_file():
        success = f'\nSuccess!\nPath to exe: {str(Path.cwd() / (Path(Path("dist") / "deeaw.exe")))}'

    # change directory back to original directory
    os.chdir(deeaw_script.parent)

    # return success message
    return success


if __name__ == "__main__":
    build = build_app()
    print(build)
