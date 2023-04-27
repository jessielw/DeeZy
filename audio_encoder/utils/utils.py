import sys
from pathlib import Path


class PrintSameLine:
    """Class to correctly print on same line"""

    def __init__(self):
        self.last_message = ""

    def print_msg(self, msg: str):
        print(" " * len(self.last_message), end="\r", flush=True)
        print(msg, end="\r", flush=True)
        self.last_message = msg


def _get_working_dir():
    """
    Used to determine the correct working directory automatically.
    This way we can utilize files/relative paths easily.

    Returns:
        (Path): Current working directory
    """
    # we're in a pyinstaller.exe bundle
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys.executable).parent

    # we're running from a *.py file
    else:
        return Path.cwd()


#TODO Re-Write this for only the tools we need
# class FindDependencies:
#     """
#     A utility class for finding and verifying dependencies required by a program.
#     It first tries to locate the dependencies beside the program,
#     then in the configuration file, and finally on the system PATH.

#     Attributes:
#         ffmpeg (str): The path to the FFmpeg executable, or None if not found.
#         mkvextract (str): The path to the mkvextract executable, or None if not found.
#         dee (str): The path to the Dee executable, or None if not found.
#         gst_launch (str): The path to the gst-launch-1.0 executable, or None if not found.

#     Args:
#         base_wd (Path): The base working directory of the program.
#     """

#     def __init__(self, base_wd: Path):
#         self.ffmpeg = None
#         self.mkvextract = None
#         self.dee = None
#         self.gst_launch = None

#         self._locate_beside_program(base_wd)

#         if None in [self.ffmpeg, self.mkvextract, self.dee, self.gst_launch]:
#             _create_config()
#             self._locate_in_config()

#         if None in [self.ffmpeg, self.mkvextract, self.dee, self.gst_launch]:
#             self._locate_on_path()

#         self._verify_dependencies(
#             [self.ffmpeg, self.mkvextract, self.dee, self.gst_launch]
#         )

#     def _locate_beside_program(self, base_wd):
#         ffmpeg_path = Path(base_wd / "apps/ffmpeg/ffmpeg.exe")
#         mkvextract_path = Path(base_wd / "apps/mkvextract/mkvextract.exe")
#         dee_path = Path(base_wd / "apps/dee/dee.exe")
#         gst_launch_path = Path(base_wd / "apps/drp/gst-launch-1.0.exe")

#         found_paths = [
#             str(path)
#             for path in [ffmpeg_path, mkvextract_path, dee_path, gst_launch_path]
#             if path.exists()
#         ]

#         for path in found_paths:
#             if str(path) == str(ffmpeg_path) and not self.ffmpeg:
#                 self.ffmpeg = str(path)
#             elif str(path) == str(mkvextract_path) and not self.mkvextract:
#                 self.mkvextract = str(path)
#             elif str(path) == str(dee_path) and not self.dee:
#                 self.dee = str(path)
#             elif str(path) == str(gst_launch_path) and not self.gst_launch:
#                 self.gst_launch = str(path)

#     def _locate_in_config(self):
#         attribute_names = ["ffmpeg", "mkvextract", "dee", "gst_launch"]
#         config_section = "tool_paths"
#         for attr_name in attribute_names:
#             value = _read_config(config_section, attr_name)
#             if value and Path(value).is_file():
#                 setattr(self, attr_name, str(value))

#     def _locate_on_path(self):
#         if self.ffmpeg is None:
#             self.ffmpeg = shutil.which("ffmpeg")
#         if self.mkvextract is None:
#             self.mkvextract = shutil.which("mkvextract")
#         if self.dee is None:
#             self.dee = shutil.which("dee")
#         if self.gst_launch is None:
#             self.gst_launch = shutil.which("gst-launch-1.0")

#     @staticmethod
#     def _verify_dependencies(dependencies: list):
#         executable_names = ["ffmpeg", "mkvextract", "dee", "gst_launch"]
#         for exe_path, exe_name in zip(dependencies, executable_names):
#             if exe_path is None or exe_path == "" or not Path(exe_path).is_file():
#                 raise FileNotFoundError(f"{exe_name} path not found")