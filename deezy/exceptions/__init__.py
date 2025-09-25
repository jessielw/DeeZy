class DeeZyError(Exception):
    """Base DeeZy error"""


class NotEnoughSpaceError(DeeZyError):
    """Custom error class to for insufficient storage"""


class PathTooLongError(DeeZyError):
    """Custom error class to for path names that are too long"""


class InvalidExtensionError(DeeZyError):
    """Custom error class for invalid file extensions"""


class ChannelMixError(DeeZyError):
    """Custom error class for invalid channel mix configurations"""


class AutoChannelDetectionError(DeeZyError):
    """Custom error class for failure to automatically calculate output channels"""


class InputFileNotFoundError(DeeZyError):
    """Custom error class for missing input files"""


class OutputFileNotFoundError(DeeZyError):
    """Custom error class for missing input files"""


class MediaInfoError(DeeZyError):
    """Custom class for MediaInfo errors"""


class DependencyNotFoundError(DeeZyError):
    """Custom exception class to call when a dependency is not found"""


class InvalidDelayError(DeeZyError):
    """Class to raise in the event of an invalid delay input"""


class OutputExistsError(DeeZyError):
    """Raised when the intended output file already exists and overwrite was not enabled."""


class InvalidAtmosInputError(DeeZyError):
    """Raised when input file is an incompatible Atmos input."""
