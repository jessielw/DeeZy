# deezy encode atmos

Captured help (abbreviated):

```
usage: DeeZy encode atmos [-h] [--ffmpeg FFMPEG] [--truehdd TRUEHDD]
                          [--dee DEE] [--track-index TRACK_INDEX]
                          [--delay DELAY] [--parse-elementary-delay]
                          [--keep-temp] [--reuse-temp-files]
                          [--temp-dir TEMP_DIR] [--output OUTPUT]
                          [--output-template OUTPUT_TEMPLATE]
                          [--output-preview] [--max-parallel MAX_PARALLEL]
                          [--jitter-ms JITTER_MS] [--max-logs N]
                          [--max-batch-results N] [--working-dir WORKING_DIR]
                          [--batch-summary-output]
                          [--batch-output-dir BATCH_OUTPUT_DIR] [--overwrite]
                          [--limit-ffmpeg LIMIT_FFMPEG]
                          [--limit-dee LIMIT_DEE]
                          [--limit-truehdd LIMIT_TRUEHDD] [--bitrate BITRATE]
                          [--drc-line-mode {film_standard,film_light,music_standard,music_light,speech}]
                          [--drc-rf-mode {film_standard,film_light,music_standard,music_light,speech}]
                          [--custom-dialnorm CUSTOM_DIALNORM]
                          [--no-dialogue-intelligence]
                          [--speech-threshold SPEECH_THRESHOLD]
                          [--metering-mode {1770_1,1770_2,1770_3,1770_4,leqa}]
                          [--lt-rt-center {+3,+1.5,0,-1.5,-3,-4.5,-6,-inf}]
                          [--lt-rt-surround {-1.5,-3,-4.5,-6,-inf}]
                          [--lo-ro-center {+3,+1.5,0,-1.5,-3,-4.5,-6,-inf}]
                          [--lo-ro-surround {-1.5,-3,-4.5,-6,-inf}]
                          [--stereo-down-mix {auto,loro,ltrt,dpl2}]
                          [--atmos-mode {streaming,bluray}]
                          [--thd-warp-mode {normal,warping,prologiciix,loro}]
                          [--bed-conform]
                          INPUT [INPUT ...]

positional arguments:
  INPUT
       Input file paths or directories

options:
  -h, --help
       show this help message and exit
  --ffmpeg, FFMPEG
       Path to FFMPEG executable.
  --truehdd, TRUEHDD
       Path to Truehdd executable.
  --dee, DEE
       Path to Dolby Encoding Engine executable.
  --track-index, TRACK_INDEX
       Track to use for encoding. Supports: 'N' (audio track N), 'a:N' (audio track N), 's:N' (stream index N).
  --delay, DELAY
       The delay in milliseconds or seconds. Note '--delay=' is required! (--delay=-10ms / --delay=10s).
  --parse-elementary-delay
       When input is an elementary (demuxed) stream, parse any delay in the filename and reset it to zero.
  --keep-temp
       Keeps the temp files after finishing.
  --reuse-temp-files
       Attempt to reuse already-extracted temp files adjacent to the input file when the extractor command is identical. This implies --keep-temp.
  --temp-dir, TEMP_DIR
       Path to store temporary files to. If not specified this will automatically happen in the temp dir of the os.
  --output, OUTPUT
       The output file path. If not specified we will attempt to automatically add Delay/Language string to output file name.
  --output-template, OUTPUT_TEMPLATE
       Optional lightweight template to control auto-generated output filenames. Supported tokens: {title},{year},{stem},{source},{lang},{channels},{worker},{delay}.
  --output-preview
       When set, render and show template-based filenames but do not write outputs. Useful to validate templates before running batch jobs.
  --max-parallel, MAX_PARALLEL
       Maximum number of files to process in parallel (default: 1).
  --jitter-ms, JITTER_MS
       Maximum random jitter in milliseconds to apply before heavy phases (FFmpeg/DEE/truehdd). Helps avoid synchronization spikes when running parallel jobs. Default 0 (disabled).
  --max-logs, N
       Maximum number of log files to keep in the working logs directory for this run. Overrides config value if provided. Use 0 to keep none.
  --max-batch-results, N
       Maximum number of batch-results JSON files to keep in the working batch-results directory for this run. Overrides config value if provided. Use 0 to keep none.
  --working-dir, WORKING_DIR
       Directory to use for DeeZy working files (logs and batch-results). Overrides config/default. If not set, uses the workspace beside the executable.
  --batch-summary-output
       Enable batch processing results summary (JSON format). Results will be saved to a 'batch-results' folder next to the executable by default.
  --batch-output-dir, BATCH_OUTPUT_DIR
       When used with --batch-summary-output, place all encoded outputs into this directory instead of writing them next to the input files.
  --overwrite
       Overwrite existing output files instead of failing.
  --limit-ffmpeg, LIMIT_FFMPEG
       Optional limit for concurrent FFmpeg processing. Defaults to --max-parallel if not set. If set higher than --max-parallel the value will be capped to --max-parallel and a warning will be emitted.
  --limit-dee, LIMIT_DEE
       Optional limit for concurrent DEE processing. Defaults to --max-parallel if not set. If set higher than --max-parallel the value will be capped to --max-parallel and a warning will be emitted.
  --limit-truehdd, LIMIT_TRUEHDD
       Optional limit for concurrent truehdd processing. Defaults to --max-parallel if not set. If set higher than --max-parallel the value will be capped to --max-parallel and a warning will be emitted.
  --bitrate, BITRATE
       The bitrate in Kbps (If too high or low for you desired layout, the bitrate will automatically be adjusted to the closest allowed bitrate).
  --drc-line-mode, {film_standard,film_light,music_standard,music_light,speech}
       Dynamic range compression settings.
  --drc-rf-mode, {film_standard,film_light,music_standard,music_light,speech}
       Dynamic range compression settings.
  --custom-dialnorm, CUSTOM_DIALNORM
       Custom dialnorm (0 disables custom dialnorm).
  --no-dialogue-intelligence
       Dialogue Intelligence enabled. Option ignored for 1770-1 or LeqA metering mode.
  --speech-threshold, SPEECH_THRESHOLD
       [0-100] If the percentage of speech is higher than the threshold, the encoder uses speech gating to set the dialnorm value. (Otherwise, the encoder uses level gating).
  --metering-mode, {1770_1,1770_2,1770_3,1770_4,leqa}
       Loudness measuring mode according to one of the broadcast standards.
  --lt-rt-center, {+3,+1.5,0,-1.5,-3,-4.5,-6,-inf}
       Lt/Rt center downmix level.
  --lt-rt-surround, {-1.5,-3,-4.5,-6,-inf}
       Lt/Rt surround downmix level.
  --lo-ro-center, {+3,+1.5,0,-1.5,-3,-4.5,-6,-inf}
       Lo/Ro center downmix level.
  --lo-ro-surround, {-1.5,-3,-4.5,-6,-inf}
       Lo/Ro surround downmix level.
  --stereo-down-mix, {auto,loro,ltrt,dpl2}
       Down mix method for stereo.
  --atmos-mode, {streaming,bluray}
       Atmos encoding mode.
  --thd-warp-mode, {normal,warping,prologiciix,loro}
       Specify warp mode when not present in metadata (truehdd).
  --bed-conform
       Enables bed conformance for Atmos content (truehd).
```

## Examples

- Encode a single file to Atmos (streaming mode):

```bash
deezy encode atmos --atmos-mode streaming --bitrate 448 "C:\\media\\scene.wav"
```

- Bluray Atmos with bed conformance and preview template:

```bash
deezy encode atmos --atmos-mode bluray --bed-conform --output-preview "C:\\media\\disc_track.wav"
```
