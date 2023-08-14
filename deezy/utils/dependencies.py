from pathlib import Path
import shutil
import platform
from typing import Union
from deezy.exceptions import DependencyNotFoundError


def get_executable_string_by_os():
    """Check executable type based on operating system"""
    operating_system = platform.system()
    if operating_system == "Windows":
        return ".exe"
    elif operating_system == "Linux":
        return ""


class Dependencies:
    ffmpeg = None
    dee = None


# TODO Re-enable some sort of config control, not sure
# how we want to do this yet.
# TODO make this better, i'm sure it can be improved to better dynamically handle
# dependencies.
class FindDependencies:
    """
    A utility class for finding and verifying dependencies required by a program.
    It first tries to locate the dependencies beside the program,
    then in the configuration file, and finally on the system PATH.

    Attributes:
        ffmpeg (str): The path to the FFmpeg executable, or None if not found.
        dee (str): The path to the Dee executable, or None if not found.

    Args:
        base_wd (Path): The base working directory of the program.
    """

    # determine os exe
    os_exe = get_executable_string_by_os()

    def get_dependencies(
        self,
        base_wd: Path,
        user_ffmpeg: Union[str, None],
        user_dee: Union[str, None],
    ):
        # check beside program
        ffmpeg, dee = self._locate_beside_program(base_wd)

        # TODO re-implement this
        # if None in [self.ffmpeg, self.mkvextract, self.dee, self.gst_launch]:
        #     _create_config()
        #     self._locate_in_config()

        if None in [ffmpeg, dee]:
            ffmpeg, dee = self._locate_on_path(ffmpeg, dee)

        # if user defines FFMPEG or DEE then let's override automatic detection
        if user_ffmpeg and user_ffmpeg.strip() != "":
            ffmpeg = Path(user_ffmpeg)

        if user_dee and user_dee.strip() != "":
            dee = Path(user_dee)

        # verify dependencies
        self._verify_dependencies([ffmpeg, dee])

        dependencies = Dependencies()
        dependencies.ffmpeg = ffmpeg
        dependencies.dee = dee

        return dependencies

    def _locate_beside_program(self, base_wd):
        ffmpeg_path = Path(base_wd / f"apps/ffmpeg/ffmpeg{self.os_exe}")
        dee_path = Path(base_wd / f"apps/dee/dee{self.os_exe}")

        # check if ffmpeg exists beside the program
        if ffmpeg_path.is_file():
            ffmpeg_path = str(ffmpeg_path)
        else:
            ffmpeg_path = None

        # check if dee exists beside the program
        if dee_path.is_file():
            dee_path = str(dee_path)
        else:
            dee_path = None

        return ffmpeg_path, dee_path

    # def _locate_in_config(self):
    #     attribute_names = ["ffmpeg", "dee"]
    #     config_section = "tool_paths"
    #     for attr_name in attribute_names:
    #         value = _read_config(config_section, attr_name)
    #         if value and Path(value).is_file():
    #             setattr(self, attr_name, str(value))

    def _locate_on_path(self, ffmpeg, dee):
        if ffmpeg is None:
            ffmpeg = shutil.which(f"ffmpeg{self.os_exe}")
        if dee is None:
            dee = shutil.which(f"dee{self.os_exe}")

        return ffmpeg, dee

    def _verify_dependencies(self, dependencies: list):
        executable_names = [f"ffmpeg{self.os_exe}", f"dee{self.os_exe}"]
        for exe_path, exe_name in zip(dependencies, executable_names):
            if exe_path is None or exe_path == "" or not Path(exe_path).is_file():
                raise DependencyNotFoundError(f"{exe_name} path not found")
