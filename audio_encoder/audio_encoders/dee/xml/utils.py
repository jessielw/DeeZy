import xmltodict
from pathlib import Path
from audio_encoder.audio_encoders.dee.xml.dd_ddp_base_xml import xml_audio_base_ddp
from audio_encoder.enums.dd import DolbyDigitalChannels
from audio_encoder.enums.ddp import DolbyDigitalPlusChannels
from typing import Union


class XMLFileNotFoundError(Exception):
    """Custom class to return if XML file output was not found"""


def _save_xml(output_dir: Path, output_file_name: Path, xml_base: dict):
    """Creates/Deletes old XML files for use with DEE

    Args:
        output_dir (Path): Full output directory
        output_file_name (Path): File name
        xml_base (dict): XML generated dictionary

    Returns:
        Path: Path to XML file for DEE
    """
    # Save out the updated template (use filename output with xml suffix)
    updated_template_file = Path(output_dir / Path(output_file_name)).with_suffix(
        ".xml"
    )

    # delete xml output template if one already exists
    if updated_template_file.exists():
        updated_template_file.unlink()

    # write new xml template for dee
    with open(updated_template_file, "w", encoding="utf-8") as xml_out:
        xml_out.write(xmltodict.unparse(xml_base, pretty=True, indent="  "))

    # check to ensure template file was created
    if updated_template_file.exists():
        return updated_template_file
    else:
        raise ValueError("XML file could not be created")


def _generate_xml_dd(
    down_mix_config: str,
    stereo_down_mix: str,
    bitrate: str,
    dd_format: str,
    channels: DolbyDigitalChannels,
    normalize: bool,
    wav_file_name: str,
    output_file_name: str,
    output_dir: Union[Path, str],
    fps: str,
):
    """Handles the parsing/creation of XML file for DEE encoding (DD/DDP)

    Args:
        down_mix_config (str): Down mix type ("off', 'mono', 'stereo', '5.1')
        stereo_down_mix (str): Can be "standard" or "dplii"
        bitrate (str): Bitrate in the format of '448'
        dd_format (str): File format, in short hand terms; "dd", "ddp" etc
        channels: (DolbyDigitalChannels): DolbyDigitalChannels variable
        normalize: (bool): True or False, if set to True we will normalize loudness
        wav_file_name (str): File name only
        output_file_name (str): File name only
        output_dir (Union[Path, str]): File path only
        fps (str): FPS of video input if it exists

    Returns:
        Path: Returns the correct path to the created template file
    """
    # Update the xml template values
    xml_base = xmltodict.parse(xml_audio_base_ddp)

    # xml wav filename/path
    xml_base["job_config"]["input"]["audio"]["wav"]["file_name"] = f'"{wav_file_name}"'
    xml_base["job_config"]["input"]["audio"]["wav"]["storage"]["local"][
        "path"
    ] = f'"{str(output_dir)}"'

    # xml ac3 file/path
    xml_base["job_config"]["output"]["ac3"]["file_name"] = f'"{output_file_name}"'
    xml_base["job_config"]["output"]["ac3"]["storage"]["local"][
        "path"
    ] = f'"{str(output_dir)}"'

    # update fps sections
    xml_base["job_config"]["input"]["audio"]["wav"]["timecode_frame_rate"] = fps
    xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["timecode_frame_rate"] = fps

    # xml temp path config
    xml_base["job_config"]["misc"]["temp_dir"]["path"] = f'"{str(output_dir)}"'

    # xml down mix config
    if down_mix_config:
        xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"][
            "downmix_config"
        ] = down_mix_config
    else:
        del xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"][
            "downmix_config"
        ]

    # TODO This is a temporary shared work around, this needs split up.
    if channels in [DolbyDigitalChannels.MONO, DolbyDigitalPlusChannels.MONO]:
        downmix_mode = "not_indicated"
    elif channels in [DolbyDigitalChannels.STEREO, DolbyDigitalPlusChannels.STEREO]:
        if stereo_down_mix == "standard":
            downmix_mode = "ltrt"
        elif stereo_down_mix == "dplii" and dd_format == "ddp":
            downmix_mode = "ltrt-pl2"
        elif stereo_down_mix == "dplii" and dd_format == "dd":
            downmix_mode = None
    elif channels in [DolbyDigitalChannels.SURROUND, DolbyDigitalPlusChannels.SURROUND]:
        downmix_mode = "loro"
    elif channels == DolbyDigitalPlusChannels.SURROUNDEX:
        downmix_mode = "not_indicated"

    # if downmix_mode is not None update the XML entry
    xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["downmix"][
        "preferred_downmix_mode"
    ] = downmix_mode

    # xml bit rate config
    xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["data_rate"] = str(bitrate)

    # file format
    if dd_format == "dd":
        xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["encoder_mode"] = "dd"
    elif dd_format == "ddp":
        # if ddp and normalize is true, set template to normalize audio
        if normalize:
            # Remove measure_only, add measure_and_correct, with default preset of atsc_a85
            del xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["loudness"][
                "measure_only"
            ]
            xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["loudness"][
                "measure_and_correct"
            ] = {}
            xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["loudness"][
                "measure_and_correct"
            ]["preset"] = "atsc_a85"

        # if channels are 8 set encoder mode to ddp71
        if channels == DolbyDigitalPlusChannels.SURROUNDEX:
            xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"][
                "encoder_mode"
            ] = "ddp71"

        # if channels are less than 8 set encoder to ddp
        else:
            xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"][
                "encoder_mode"
            ] = "ddp"

        # set output mode
        xml_base["job_config"]["output"]["ec3"] = xml_base["job_config"]["output"][
            "ac3"
        ]

        # delete ac3 from dict
        del xml_base["job_config"]["output"]["ac3"]
    else:
        raise ValueError("Unknown file format.")

    # create XML and return path to XML
    updated_template_file = _save_xml(
        output_dir=output_dir, output_file_name=output_file_name, xml_base=xml_base
    )

    # check path of xml file
    if not updated_template_file.is_file():
        raise XMLFileNotFoundError("Could not locate file path to XML.")
    else:
        return updated_template_file
