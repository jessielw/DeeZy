# DeeZy

In it's current form it's designed around encoding audio with Dolby Engine Encoder.

However, it was designed with expandability as needed for other encoders.

Everything is functional, DeeZy is still in beta until everything has been thoroughly tested, as far as handling errors etc.

## Install (no install needed it's portable)

At the moment you'll need to download your binary (Windows 8+ x64 or Linux) and handle this one of two ways.

1. You can add both FFMPEG and dee.exe (Dolby Encoding Engine) to your system PATH and use DeeZy as a normal executable.

2. Create an `apps` folder beside DeeZy with two nested directories `ffmpeg` and `dee`

```
deezy (executable)
- apps
    - ffmpeg
    - dee
```

You can place the executables to those files and needed libraries in the folders and then use DeeZy as a normal executable.

## Uninstall

Delete files.

## Basic Usage

```
usage: DeeZy [-h] [-v] {encode,find,info} ...

positional arguments:
  {encode,find,info}

options:
  -h, --help          show this help message and exit
  -v, --version       show program's version number and exit
```

## Encode Usage DD

```
usage: DeeZy encode dd [-h] [-t TRACK_INDEX] [-b BITRATE] [-d DELAY] [-k]
                       [-p {STANDARD[0],DEBUG[1],SILENT[3]}] [-tmp TEMP_DIR]
                       [-o OUTPUT] [-s {STANDARD[0],DPLII[1]}]
                       [-c {MONO[1],STEREO[2],SURROUND[6]}]
                       [-drc {FILM_STANDARD[film_standard],FILM_LIGHT[film_light],MUSIC_STANDARD[music_standard],MUSIC_LIGHT[music_light],SPEECH[speech]}]
                       INPUT [INPUT ...]

positional arguments:
  INPUT
   Input file paths or directories

options:
  -h, --help
   show this help message and exit
  -t, --track-index, TRACK_INDEX
   The index of the audio track to use.
  -b, --bitrate, BITRATE
   The bitrate in Kbps.
  -d, --delay, DELAY
   The delay in milliseconds or seconds. Note '-d=' is required! (-d=-10ms / -d=10s).
  -k, --keep-temp
   Keeps the temp files after finishing (usually a wav and an xml for DEE).
  -p, --progress-mode, {STANDARD[0],DEBUG[1],SILENT[3]}
   Sets progress output mode verbosity.
  -tmp, --temp-dir, TEMP_DIR
   Path to store temporary files to. If not specified this will automatically happen in the temp dir of the os.
  -o, --output, OUTPUT
   The output file path. If not specified we will attempt to automatically add Delay/Language string to output file name.
  -s, --stereo-down-mix, {STANDARD[0],DPLII[1]}
   Down mix method for stereo.
  -c, --channels, {MONO[1],STEREO[2],SURROUND[6]}
   The number of channels.
  -drc, --dynamic-range-compression, {FILM_STANDARD[film_standard],FILM_LIGHT[film_light],MUSIC_STANDARD[music_standard],MUSIC_LIGHT[music_light],SPEECH[speech]}
   Dynamic range compression settings.
```

## Encode Usage DDP

```
usage: DeeZy encode ddp [-h] [-t TRACK_INDEX] [-b BITRATE] [-d DELAY] [-k]
                        [-p {STANDARD[0],DEBUG[1],SILENT[3]}] [-tmp TEMP_DIR]
                        [-o OUTPUT] [-s {STANDARD[0],DPLII[1]}]
                        [-c {MONO[1],STEREO[2],SURROUND[6],SURROUNDEX[8]}]
                        [-n]
                        [-drc {FILM_STANDARD[film_standard],FILM_LIGHT[film_light],MUSIC_STANDARD[music_standard],MUSIC_LIGHT[music_light],SPEECH[speech]}]
                        INPUT [INPUT ...]

positional arguments:
  INPUT
   Input file paths or directories

options:
  -h, --help
   show this help message and exit
  -t, --track-index, TRACK_INDEX
   The index of the audio track to use.
  -b, --bitrate, BITRATE
   The bitrate in Kbps.
  -d, --delay, DELAY
   The delay in milliseconds or seconds. Note '-d=' is required! (-d=-10ms / -d=10s).
  -k, --keep-temp
   Keeps the temp files after finishing (usually a wav and an xml for DEE).
  -p, --progress-mode, {STANDARD[0],DEBUG[1],SILENT[3]}
   Sets progress output mode verbosity.
  -tmp, --temp-dir, TEMP_DIR
   Path to store temporary files to. If not specified this will automatically happen in the temp dir of the os.
  -o, --output, OUTPUT
   The output file path. If not specified we will attempt to automatically add Delay/Language string to output file name.
  -s, --stereo-down-mix, {STANDARD[0],DPLII[1]}
   Down mix method for stereo.
  -c, --channels, {MONO[1],STEREO[2],SURROUND[6],SURROUNDEX[8]}
   The number of channels.
  -n, --normalize
   Normalize audio for DDP.
  -drc, --dynamic-range-compression, {FILM_STANDARD[film_standard],FILM_LIGHT[film_light],MUSIC_STANDARD[music_standard],MUSIC_LIGHT[music_light],SPEECH[speech]}
   Dynamic range compression settings.
```

## Find Usage

```
usage: DeeZy find [-h] [-n] INPUT [INPUT ...]

positional arguments:
  INPUT       Input file paths or directories

options:
  -h, --help  show this help message and exit
  -n, --name  Only display names instead of full paths.
```

Example:

```
deezy find "Path\*.*"
Path\Men.in.Black.3.2012.UHD.BluRay.2160p.TrueHD.Atmos.7.1.DV.HEVC.HYBRID.REMUX.mkv
```

## Info Usage

```
usage: DeeZy info [-h] INPUT [INPUT ...]

positional arguments:
  INPUT       Input file paths or directories

options:
  -h, --help  show this help message and exit
```

Example:

```
deezy info "Path\Avatar.The.Last.Airbender.S01E01.The.Boy.in.the.Iceberg.mkv"
File: Avatar.The.Last.Airbender.S01E01.The.Boy.in.the.Iceberg.mkv
Audio tracks: [1]
------------------------------------------------------------------------------------------
Track               : 1
Codec               : FLAC - (flac)
Channels            : 2.0 - L R
Bit rate mode       : VBR / Variable
Bit rate            : 760 kb/s
Sampling Rate       : 48.0 kHz
Duration            : 23 min 40 s
Language            : English
Title               : FLAC 2.0
Stream size         : 128.7 MiB
Bit Depth           : 24 bits
Compression         : Lossless
Default             : Yes
Forced              : No
------------------------------------------------------------------------------------------
```

`Track ... : 1` corresponds to the `-t / --track-index` arg when selecting your track to encode with dd/ddp

## Input Types

```
You can line up multiple inputs to be encoded with the same settings:
input.mkv input.mp4 etc...
If there is space in the name you'll likely want to wrap them in quotes

It also supports everything the python glob module supports. This allows you to filter or search recursively etc:

Will find all mkv's in that currently directory:
"directory/nested_path/*.mkv"

Will find all mkv's recursively:
"directory/nested_path/**/*.mkv"

```
