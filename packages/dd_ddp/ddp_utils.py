import xmltodict
from pathlib import Path
from packages.dd_ddp.xml_base import xml_audio_base_ddp
from packages.shared.shared_utils import save_xml
from typing import Union
from argparse import ArgumentTypeError


def generate_xml_dd(
    down_mix_config: str,
    stereo_down_mix: str,
    bitrate: str,
    dd_format: str,
    channels: int,
    normalize: bool,
    wav_file_name: str,
    output_file_name: str,
    output_dir: Union[Path, str],
):
    """Handles the parsing/creation of XML file for DEE encoding (DD/DDP)

    Args:
        down_mix_config (str): Down mix type ("off', 'mono', 'stereo', '5.1')
        stereo_down_mix (str): Can be "standard" or "dplii"
        bitrate (str): Bitrate in the format of '448'
        dd_format (str): File format, in short hand terms; "dd", "ddp" etc
        channels: (int): Channels in the format of 1, 2 etc
        normalize: (bool): True or False, if set to True we will normalize loudness
        wav_file_name (str): File name only
        output_file_name (str): File name only
        output_dir (Union[Path, str]): File path only

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

    # xml temp path config
    xml_base["job_config"]["misc"]["temp_dir"]["path"] = f'"{str(output_dir)}"'

    # xml down mix config
    xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"][
        "downmix_config"
    ] = down_mix_config

    if channels == 1:
        downmix_mode = "not_indicated"
    elif channels == 2:
        if stereo_down_mix == "standard":
            downmix_mode = "ltrt"
        elif stereo_down_mix == "dplii" and dd_format == "ddp":
            downmix_mode = "ltrt-pl2"
        elif stereo_down_mix == "dplii" and dd_format == "dd":
            downmix_mode = None
    elif channels >= 6:
        downmix_mode = "loro"

    # if downmix_mode is not None update the XML entry
    if downmix_mode:
        xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["downmix"][
            "preferred_downmix_mode"
        ] = downmix_mode

    # if downmix_mode is None delete XML entry completely
    elif not downmix_mode:
        del xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["downmix"]

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
        if channels == 8:
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
        raise ArgumentTypeError("Unknown file format.")

    # create XML and return path to XML
    updated_template_file = save_xml(
        output_dir=output_dir, output_file_name=output_file_name, xml_base=xml_base
    )

    return updated_template_file
