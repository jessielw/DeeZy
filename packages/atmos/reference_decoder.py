import argparse
import pathlib
import dataclasses
import subprocess

CHANNELS = {
    '2.0': {
        'id': 0,
        'names': ['L', 'R'],
    },
    '3.1': {
        'id': 3,
        'names': ['L', 'R', 'C', 'LFE'],
    },
    '5.1': {
        'id': 7,
        'names': ['L', 'R', 'C', 'LFE', 'Ls', 'Rs'],
    },
    '7.1': {
        'id': 11,
        'names': ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Lrs', 'Rrs'],
    },
    '9.1': {
        'id': 12,
        'names': ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Lrs', 'Rrs', 'Lw', 'Rw'],
    },
    '5.1.2': {
        'id': 13,
        'names': ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Ltm', 'Rtm'],
    },
    '5.1.4': {
        'id': 14,
        'names': ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Ltf', 'Rtf', 'Ltr', 'Rtr'],
    },
    '7.1.2': {
        'id': 15,
        'names': ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Lrs', 'Rrs', 'Ltm', 'Rtm'],
    },
    '7.1.4': {
        'id': 16,
        'names': ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Lrs', 'Rrs', 'Ltf', 'Rtf', 'Ltr', 'Rtr'],
    },
    '7.1.6': {
        'id': 17,
        'names': ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Lrs', 'Rrs', 'Ltf', 'Rtf', 'Ltm', 'Rtm', 'Ltr', 'Rtr'],
    },
    '9.1.2': {
        'id': 18,
        'names': ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Lrs', 'Rrs', 'Lw', 'Rw', 'Ltm', 'Rtm'],
    },
    '9.1.4': {
        'id': 19,
        'names': ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Lrs', 'Rrs', 'Lw', 'Rw', 'Ltf', 'Rtf', 'Ltr', 'Rtr'],
    },
    '9.1.6': {
        'id': 20,
        'names': ['L', 'R', 'C', 'LFE', 'Ls', 'Rs', 'Lrs', 'Rrs', 'Lw', 'Rw', 'Ltf', 'Rtf', 'Ltm', 'Rtm', 'Ltr', 'Rtr'],
    },
}


@dataclasses.dataclass
class Config:
    gst_launch: pathlib.Path
    channels: str
    no_numbers: bool
    single: bool


class AtmosDecode:
    def __init__(self, config: Config):
        if not config.gst_launch.is_file():
            raise RuntimeError(f'Incorrect path to gst-launch-1.0.exe: {config.gst_launch.absolute()}')
        self.config: Config = config

    def decode(self, input_file: pathlib.Path, out_file: pathlib.Path | None = None):
        if not input_file.is_file():
            raise RuntimeError(f'Input file {input_file.absolute()} is not a file')

        with input_file.open('rb') as f:
            first_bytes = f.read(10)

            eac3_sync_word = 0x0B77.to_bytes(2, 'big')
            truehd_sync_word = 0xF8726FBA.to_bytes(4, 'big')

            if first_bytes.startswith(eac3_sync_word):
                command_fun = self.prepare_eac3_decode_command
            elif truehd_sync_word in first_bytes:
                command_fun = self.prepare_truehd_decode_command
            else:
                raise RuntimeError(f'Source file must be in E-AC3 or TrueHD format')

        channel_layout = CHANNELS[self.config.channels]
        out_channel_config_id, channel_names = channel_layout['id'], channel_layout['names']

        processes = []
        for channel_id, channel_name in enumerate(channel_names):
            if self.config.no_numbers:
                suffix = f'.{channel_name}.wav'
            else:
                suffix = f'.{str(channel_id + 1).zfill(2)}_{channel_name}.wav'

            out_file_path = out_file.with_suffix(suffix) if out_file is not None else input_file.with_suffix(suffix)

            command = command_fun(input_file, out_file_path, channel_id, out_channel_config_id)

            if self.config.single:
                print(f'Decoding "{out_file_path}"')
                subprocess.run(command)
            else:
                processes.append(subprocess.Popen(command))

        if not self.config.single:
            for process in processes:
                process.wait()

    def prepare_eac3_decode_command(
            self,
            input_file: pathlib.Path,
            out_file: pathlib.Path,
            channel_id: int,
            out_channel_config_id: int
    ) -> list[str]:

        return [
            str(self.config.gst_launch.absolute()),
            '--gst-plugin-path', f'{self.config.gst_launch.parent.absolute()}/gst-plugins',
            'filesrc', f'location={self._prepare_file_path(input_file)}', '!',
            'dlbac3parse', '!',
            'dlbaudiodecbin', f'out-ch-config={out_channel_config_id}', '!',
            'deinterleave', 'name=d', f'd.src_{channel_id}', '!',
            'wavenc', '!',
            'filesink', f'location={self._prepare_file_path(out_file)}'
        ]

    def prepare_truehd_decode_command(
            self,
            input_file: pathlib.Path,
            out_file: pathlib.Path,
            channel_id: int,
            out_channel_config_id: int
    ) -> list[str]:

        return [
            str(self.config.gst_launch.absolute()),
            '--gst-plugin-path', f'{self.config.gst_launch.parent.absolute()}/gst-plugins',
            'filesrc', f'location={self._prepare_file_path(input_file)}', '!',
            'dlbtruehdparse', 'align-major-sync=false', '!',
            'dlbaudiodecbin', 'truehddec-presentation=16', f'out-ch-config={out_channel_config_id}', '!',
            'deinterleave', 'name=d', f'd.src_{channel_id}', '!',
            'wavenc', '!',
            'filesink', f'location={self._prepare_file_path(out_file)}'
        ]

    def _prepare_file_path(self, source: pathlib.Path) -> str:
        return str(source.absolute()).replace('\\', '\\\\')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-i', '--input',
        help='Path to source file',
        type=pathlib.Path,
        required=True,
    )
    parser.add_argument(
        '-o', '--output',
        help='Path to output base file',
        type=pathlib.Path,
    )
    parser.add_argument(
        '--gst_launch',
        help='Path to gst-launch file from Dolby Reference Player',
        type=pathlib.Path,
        default=pathlib.Path(r'C:\Program Files\Dolby\Dolby Reference Player\gst-launch-1.0.exe')
    )
    parser.add_argument(
        '-c', '--channels',
        help='Output channel configuration',
        type=str,
        default='9.1.6',
        choices=CHANNELS.keys(),
    )
    parser.add_argument(
        '-nn', '--no_numbers',
        help='Do not use numbers in output channel names',
        action='store_true',
    )
    parser.add_argument(
        '-s', '--single',
        help='Decode one channel at a time',
        action='store_true',
    )
    args = parser.parse_args()
    args_dataclass = Config(
        gst_launch=args.gst_launch,
        channels=args.channels,
        no_numbers=args.no_numbers,
        single=args.single,
    )

    decoder = AtmosDecode(args_dataclass)
    decoder.decode(args.input, args.output)


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as e:
        print(e)
