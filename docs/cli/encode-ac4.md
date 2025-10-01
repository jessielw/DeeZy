# deezy encode ac4

```text {.scrollable-code-block}
usage: DeeZy encode ac4 [-h] [--ffmpeg FFMPEG] [--truehdd TRUEHDD] [--dee DEE]
                        [--track-index TRACK_INDEX] [--delay DELAY]
                        [--keep-temp] [--reuse-temp-files]
                        [--temp-dir TEMP_DIR] [--output OUTPUT]
                        [--output-template OUTPUT_TEMPLATE] [--output-preview]
                        [--max-parallel MAX_PARALLEL] [--jitter-ms JITTER_MS]
                        [--max-logs N] [--max-batch-results N]
                        [--working-dir WORKING_DIR] [--batch-summary-output]
                        [--batch-output-dir BATCH_OUTPUT_DIR] [--overwrite]
                        [--limit-ffmpeg LIMIT_FFMPEG] [--limit-dee LIMIT_DEE]
                        [--limit-truehdd LIMIT_TRUEHDD] [--bitrate BITRATE]
                        [--no-dialogue-intelligence]
                        [--speech-threshold SPEECH_THRESHOLD]
                        [--metering-mode {1770_1,1770_2,1770_3,1770_4,leqa}]
                        [--ims-legacy-presentation]
                        [--encoding-profile {ims,ims_music}]
                        [--ddp-drc {film_standard,film_light,music_standard,music_light,speech,none}]
                        [--flat-panel-drc {film_standard,film_light,music_standard,music_light,speech,none}]
                        [--home-theatre-drc {film_standard,film_light,music_standard,music_light,speech,none}]
                        [--portable-headphones-drc {film_standard,film_light,music_standard,music_light,speech,none}]
                        [--portable-speakers-drc {film_standard,film_light,music_standard,music_light,speech,none}]
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
  --keep-temp
       Keeps the temp files after finishing.
  --reuse-temp-files
       Attempt to reuse already-extracted temp files adjacent to the input file when the extractor command is identical. This implies --keep-temp.
  --temp-dir, TEMP_DIR
       Path to store temporary files to. If not specified this will automatically happen in the temp dir of the os.
  --output, OUTPUT
       The output file path. If not specified we will attempt to automatically add Delay/Language string to output file name.
  --output-template, OUTPUT_TEMPLATE
     Optional lightweight template to control auto-generated output filenames. Supported tokens: {title},{year},{stem},{source},{lang},{channels},{worker},{delay},{opt-delay}.
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
  --no-dialogue-intelligence
       Dialogue Intelligence enabled. Option ignored for 1770-1 or LeqA metering mode.
  --speech-threshold, SPEECH_THRESHOLD
       [0-100] If the percentage of speech is higher than the threshold, the encoder uses speech gating to set the dialnorm value. (Otherwise, the encoder uses level gating).
  --metering-mode, {1770_1,1770_2,1770_3,1770_4,leqa}
       Loudness measuring mode according to one of the broadcast standards.
  --ims-legacy-presentation
       Determines whether the Dolby AC-4 encoder inserts an additional presentation for backward compatibility.
  --encoding-profile, {ims,ims_music}
       Encoding profile. For encoding music content, select ims_music.
  --ddp-drc, {film_standard,film_light,music_standard,music_light,speech,none}
       Dynamic range compression settings for AC4.
  --flat-panel-drc, {film_standard,film_light,music_standard,music_light,speech,none}
       Dynamic range compression settings for AC4.
  --home-theatre-drc, {film_standard,film_light,music_standard,music_light,speech,none}
       Dynamic range compression settings for AC4.
  --portable-headphones-drc, {film_standard,film_light,music_standard,music_light,speech,none}
       Dynamic range compression settings for AC4.
  --portable-speakers-drc, {film_standard,film_light,music_standard,music_light,speech,none}
       Dynamic range compression settings for AC4.
  --thd-warp-mode, {normal,warping,prologiciix,loro}
       Specify warp mode when not present in metadata (truehdd).
  --bed-conform
       Enables bed conformance for Atmos content (truehd).
```

## Examples

- Encode AC-4 in streaming mode (basic):

```bash
deezy encode ac4 --bitrate 384 "C:\\media\\song.wav"
```

- Encode using preset options for AC-4 (if preset exists):

```bash
deezy encode preset my-ac4-preset "C:\\media\\song.wav"
```
