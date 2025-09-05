import argparse
from pathlib import Path
from typing import Any

import tomlkit

from deezy.config.defaults import DEFAULT_CONFIG, get_default_config_path


class ConfigGenerator:
    """Generates DeeZy configuration files."""

    __slots__ = ()

    @staticmethod
    def generate_default_config(
        output_path: Path | None = None, overwrite: bool = False
    ) -> Path:
        """Generate a default configuration file.

        Args:
            output_path: Where to save the config, or None for default location
            overwrite: Whether to overwrite existing files

        Returns:
            Path where config was saved

        Raises:
            FileExistsError: If file exists and overwrite=False
            Exception: If unable to write file
        """
        if output_path is None:
            output_path = get_default_config_path()

        if output_path.exists() and not overwrite:
            raise FileExistsError(f"Config file already exists: {output_path}")

        # ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # create TOML document with comments
        doc = ConfigGenerator._create_toml_document()

        # write to file using tomlkit.dumps()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(doc))

        return output_path

    @staticmethod
    def generate_config_from_args(
        args: argparse.Namespace,
        output_path: Path | None = None,
        overwrite: bool = False,
    ) -> Path:
        """Generate configuration file from CLI arguments.

        Args:
            args: Parsed CLI arguments
            output_path: Where to save the config, or None for default location
            overwrite: Whether to overwrite existing files

        Returns:
            Path where config was saved
        """
        if output_path is None:
            output_path = get_default_config_path()

        if output_path.exists() and not overwrite:
            raise FileExistsError(f"Config file already exists: {output_path}")

        # start with defaults
        config = DEFAULT_CONFIG.copy()

        # update with CLI args
        ConfigGenerator._update_config_from_args(config, args)

        # ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # write to file using tomlkit.dumps()
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(tomlkit.dumps(config))

        return output_path

    @staticmethod
    def _create_toml_document() -> Any:
        """Create a TOML document with default config and comments."""
        doc = tomlkit.document()

        # add header comment
        doc.add(tomlkit.comment("DeeZy Configuration File"))
        doc.add(tomlkit.comment("https://github.com/jessielw/DeeZy"))
        doc.add(tomlkit.nl())

        # dependencies section
        deps_table = tomlkit.table()
        deps_table.add(
            tomlkit.comment("Paths to external tools (leave empty for auto-detection)")
        )
        deps_table["ffmpeg"] = ""
        deps_table["dee"] = ""
        deps_table["truehdd"] = ""

        doc["dependencies"] = deps_table
        doc.add(tomlkit.nl())

        # defaults section
        defaults_table = tomlkit.table()

        # global defaults
        global_table = tomlkit.table()
        global_table.add(tomlkit.comment("Global encoding defaults"))
        global_table["progress_mode"] = DEFAULT_CONFIG["defaults"]["global"][
            "progress_mode"
        ]
        global_table["keep_temp"] = DEFAULT_CONFIG["defaults"]["global"]["keep_temp"]
        global_table["temp_dir"] = DEFAULT_CONFIG["defaults"]["global"]["temp_dir"]
        global_table["track_index"] = DEFAULT_CONFIG["defaults"]["global"][
            "track_index"
        ]

        # DD defaults
        dd_table = tomlkit.table()
        dd_table.add(tomlkit.comment("Dolby Digital encoding defaults"))
        dd_config = DEFAULT_CONFIG["defaults"]["dd"]
        for key, value in dd_config.items():
            dd_table[key] = value

        # DDP defaults
        ddp_table = tomlkit.table()
        ddp_table.add(tomlkit.comment("Dolby Digital Plus encoding defaults"))
        ddp_config = DEFAULT_CONFIG["defaults"]["ddp"]
        for key, value in ddp_config.items():
            ddp_table[key] = value

        defaults_table["global"] = global_table
        defaults_table["dd"] = dd_table
        defaults_table["ddp"] = ddp_table

        doc["defaults"] = defaults_table
        doc.add(tomlkit.nl())

        # presets section
        presets_table = tomlkit.table()
        presets_table.add(tomlkit.comment("User-defined encoding presets"))
        presets_table.add(tomlkit.comment("Example:"))
        presets_table.add(
            tomlkit.comment(
                'streaming = { format = "ddp", channels = "5.1", bitrate = 768 }'
            )
        )
        presets_table.add(
            tomlkit.comment(
                'bluray_atmos = { format = "ddp", channels = "ATMOS_7_1_4", bitrate = 1664, atmos = true }'
            )
        )

        doc["presets"] = presets_table

        return doc

    @staticmethod
    def _update_config_from_args(
        config: dict[str, Any], args: argparse.Namespace
    ) -> None:
        """Update configuration with values from CLI arguments.

        Args:
            config: Configuration dictionary to update
            args: Parsed CLI arguments
        """
        # update dependency paths if provided
        if hasattr(args, "ffmpeg") and args.ffmpeg:
            config["dependencies"]["ffmpeg"] = args.ffmpeg
        if hasattr(args, "dee") and args.dee:
            config["dependencies"]["dee"] = args.dee
        if hasattr(args, "truehd") and args.truehd:
            config["dependencies"]["truehd"] = args.truehd

        # determine format type
        format_type = None
        if hasattr(args, "format_command"):
            format_type = args.format_command

        if not format_type:
            return

        # update global defaults
        global_defaults = config["defaults"]["global"]
        if hasattr(args, "progress_mode") and args.progress_mode:
            global_defaults["progress_mode"] = args.progress_mode.name
        if hasattr(args, "keep_temp"):
            global_defaults["keep_temp"] = args.keep_temp
        if hasattr(args, "temp_dir") and args.temp_dir:
            global_defaults["temp_dir"] = args.temp_dir
        if hasattr(args, "track_index"):
            global_defaults["track_index"] = args.track_index

        # update format-specific defaults
        if format_type in config["defaults"]:
            format_defaults = config["defaults"][format_type]

            if hasattr(args, "channels") and args.channels:
                format_defaults["channels"] = args.channels.name
            if hasattr(args, "bitrate") and args.bitrate:
                format_defaults["bitrate"] = args.bitrate
            if (
                hasattr(args, "dynamic_range_compression")
                and args.dynamic_range_compression
            ):
                format_defaults["drc"] = args.dynamic_range_compression.name
            if hasattr(args, "stereo_down_mix") and args.stereo_down_mix:
                format_defaults["stereo_down_mix"] = args.stereo_down_mix.name

            # DDP-specific options
            if format_type == "ddp":
                if hasattr(args, "normalize"):
                    format_defaults["normalize"] = args.normalize
                if hasattr(args, "atmos"):
                    format_defaults["atmos"] = args.atmos
                if hasattr(args, "no_bed_conform"):
                    format_defaults["no_bed_conform"] = args.no_bed_conform
