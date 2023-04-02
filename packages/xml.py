import xmltodict
from pathlib import Path
from packages.xml_base import xml_audio_base_ddp
from typing import Union


def generate_xml(
    down_mix_config: str,
    bitrate: str,
    dd_format: str,
    channels: int,
    wav_file_name: str,
    output_file_name: str,
    output_dir: Union[Path, str],
):
    """Handles the parsing/creation of XML file for dee

    Args:
        down_mix_config (str): Down mix type ("off', 'mono', 'stereo', '5.1')
        bitrate (str): Bitrate in the format of '448'
        dd_format (str): File format, in short hand terms; "dd", "ddp" etc
        wav_file_name (str): File name only
        output_file_name (str): File name only
        output_dir (Union[Path, str]): File path only

    Returns:
        Path: Returns the correct path to the created template file
    """
    # Update the xml template values
    xml_base = xmltodict.parse(xml_audio_base_ddp)

    # xml down mix config
    xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"][
        "downmix_config"
    ] = down_mix_config
    xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["data_rate"] = str(bitrate)

    # xml wav config
    xml_base["job_config"]["input"]["audio"]["wav"]["file_name"] = f'"{wav_file_name}"'
    xml_base["job_config"]["input"]["audio"]["wav"]["storage"]["local"][
        "path"
    ] = f'"{str(output_dir)}"'

    # xml ac3 config
    xml_base["job_config"]["output"]["ac3"]["file_name"] = f'"{output_file_name}"'
    xml_base["job_config"]["output"]["ac3"]["storage"]["local"][
        "path"
    ] = f'"{str(output_dir)}"'

    # xml temp path config
    xml_base["job_config"]["misc"]["temp_dir"]["path"] = f'"{str(output_dir)}"'

    # file format
    if dd_format == "dd":
        xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["encoder_mode"] = "dd"
    elif dd_format == "ddp":

        # Remove measure_only, add measure_and_correct, with default present of atsc_a85
        del xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["loudness"][
            "measure_only"
        ]
        xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["loudness"][
            "measure_and_correct"
        ] = {}
        xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"]["loudness"][
            "measure_and_correct"
        ]["preset"] = "atsc_a85"

        if channels == 8:
            xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"][
                "encoder_mode"
            ] = "ddp71"
        else:
            xml_base["job_config"]["filter"]["audio"]["pcm_to_ddp"][
                "encoder_mode"
            ] = "ddp"
        xml_base["job_config"]["output"]["ec3"] = xml_base["job_config"]["output"][
            "ac3"
        ]
        del xml_base["job_config"]["output"]["ac3"]
    else:
        raise Exception("Unknown file format.")

    # Save out the updated template (use ac3 output with xml suffix)
    updated_template_file = Path(output_dir / Path(output_file_name)).with_suffix(
        ".xml"
    )

    # delete xml output template if one already exists
    if updated_template_file.exists():
        updated_template_file.unlink()

    # write new xml template for dee
    with open(updated_template_file, "w", encoding="utf-8") as xml_out:
        xml_out.write(xmltodict.unparse(xml_base, pretty=True, indent="  "))

    return updated_template_file
