# DeeZy

In it's current form it's designed around encoding audio with Dolby Engine Encoder.
However, it was designed with expandability as needed for other encoders.

## Install (no install needed it's portable)

At the moment you'll need to download your binary (Windows 8+ x64 or Linux) and handle this one of two ways.

1. You can add both FFMPEG and dee.exe (Dolby Encoding Engine) to your system PATH and use DeeZy as a normal executable.

2. Create an `apps` folder beside DeeZy with two nested directories `ffmpeg` and `dee`

```
- deezy
- apps
    - ffmpeg
    - dee
```

You can place the executables to those files and needed libraries in the folders and then use DeeZy as a normal executable.

## Uninstall

Delete files.

## Basic Usage

```bash
usage: DeeZy [-h] [-v] {encode,find,info} ...

positional arguments:
  {encode,find,info}

options:
  -h, --help          show this help message and exit
  -v, --version       show program's version number and exit
```

## Encode Usage DD

```bash
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

```bash
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

```bash
usage: DeeZy find [-h] [-n] INPUT [INPUT ...]

positional arguments:
  INPUT       Input file paths or directories

options:
  -h, --help  show this help message and exit
  -n, --name  Only display names instead of full paths.
```

## Find Usage

```bash
usage: DeeZy find [-h] [-n] INPUT [INPUT ...]

positional arguments:
  INPUT       Input file paths or directories

options:
  -h, --help  show this help message and exit
  -n, --name  Only display names instead of full paths.
```

## Info Usage

```bash
usage: DeeZy info [-h] INPUT [INPUT ...]

positional arguments:
  INPUT       Input file paths or directories

options:
  -h, --help  show this help message and exit
```
