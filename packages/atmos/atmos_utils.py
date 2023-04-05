from typing import Union
import xmltodict
from packages.atmos.xml_base import xml_audio_base_atmos
from packages.shared.shared_utils import save_xml
from pathlib import Path


def generate_xml_atmos(
    bitrate: str,
    normalize: bool,
    wav_file_name: str,
    output_file_name: str,
    output_dir: Union[Path, str],
):
    """Handles the parsing/creation of XML file for DEE encoding (atmos)
    Args:
        bitrate (str): Bitrate in the format of '448'
        normalize: (bool): True or False, if set to True we will normalize loudness
        wav_file_name (str): File name only
        output_file_name (str): File name only
        output_dir (Union[Path, str]): File path only
    Returns:
        Path: Returns the correct path to the created template file
    """
    # Update the xml template values
    xml_base = xmltodict.parse(xml_audio_base_atmos)

    # xml wav filename/path
    xml_base["job_config"]["input"]["audio"]["wav"]["file_name"] = f'"{wav_file_name}"'
    xml_base["job_config"]["input"]["audio"]["wav"]["storage"]["local"][
        "path"
    ] = f'"{str(output_dir)}"'

    # xml eac3 filename/path
    xml_base["job_config"]["output"]["ec3"]["file_name"] = f'"{output_file_name}"'
    xml_base["job_config"]["output"]["ec3"]["storage"]["local"][
        "path"
    ] = f'"{str(output_dir)}"'

    # xml temp path config
    xml_base["job_config"]["misc"]["temp_dir"]["path"] = f'"{str(output_dir)}"'

    # # xml down mix config
    # xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"][
    #     "downmix_config"
    # ] = down_mix_config

    # if channels == 1:
    #     downmix_mode = "not_indicated"
    # elif channels == 2:
    #     if stereo_down_mix == "standard":
    #         downmix_mode = "ltrt"
    #     elif stereo_down_mix == "dplii":
    #         downmix_mode = "ltrt-pl2"
    # elif channels >= 6:
    #     downmix_mode = "loro"
    # xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["downmix"][
    #     "preferred_downmix_mode"
    # ] = downmix_mode

    # xml bitrate config
    xml_base["job_config"]["filter"]["audio"]["encode_to_atmos_ddp"]["data_rate"] = str(
        bitrate
    )

    # if normalize is true, set template to normalize audio
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

    # create XML and return path to XML
    updated_template_file = save_xml(
        output_dir=output_dir, output_file_name=output_file_name, xml_base=xml_base
    )

    return updated_template_file
