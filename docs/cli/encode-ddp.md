````markdown
# deezy encode ddp

Captured help (abbreviated):

```
usage: DeeZy encode ddp [-h] [--ffmpeg FFMPEG] [--truehdd TRUEHDD] [--dee DEE]
                        [--track-index TRACK_INDEX] [--delay DELAY]
                        [--parse-elementary-delay] [--keep-temp]
                        [--reuse-temp-files] [--temp-dir TEMP_DIR]
                        [--output OUTPUT] [--output-template OUTPUT_TEMPLATE]
                        [--output-preview] [--max-parallel MAX_PARALLEL]
                        [--jitter-ms JITTER_MS] [--max-logs N]
                        [--max-batch-results N] [--working-dir WORKING_DIR]
                        [--batch-summary-output]
                        [--batch-output-dir BATCH_OUTPUT_DIR] [--overwrite]
                        [--limit-ffmpeg LIMIT_FFMPEG] [--limit-dee LIMIT_DEE]
                        [--limit-truehdd LIMIT_TRUEHDD] [--bitrate BITRATE]
                        [--drc-line-mode {film_standard,film_light,music_standard,music_light,speech}]
                        [--drc-rf-mode {film_standard,film_light,music_standard,music_light,speech}]
                        [--custom-dialnorm CUSTOM_DIALNORM]
                        [--no-dialogue-intelligence]
                        [--speech-threshold SPEECH_THRESHOLD]
                        [--metering-mode {1770_1,1770_2,1770_3,leqa}]
                        [--no-low-pass-filter] [--no-surround-3db]
                        [--no-surround-90-deg-phase-shift]
                        [--stereo-down-mix {auto,loro,ltrt,dpl2}]
                        [--lt-rt-center {+3,+1.5,0,-1.5,-3,-4.5,-6,-inf}]
                        [--lt-rt-surround {-1.5,-3,-4.5,-6,-inf}]
                        [--lo-ro-center {+3,+1.5,0,-1.5,-3,-4.5,-6,-inf}]
                        [--lo-ro-surround {-1.5,-3,-4.5,-6,-inf}]
                        [--channels {0,1,2,6,8}]
                        INPUT [INPUT ...]
```

## Examples

- Encode a directory of inputs to DDP with 3 parallel workers and write outputs to a batch dir:

```powershell
uv run python -m deezy encode ddp "C:\\media\\album\\" --max-parallel 3 --batch-summary-output --batch-output-dir "C:\\out\\ddp"
```

- Force stereo output and preview filename template:

```powershell
uv run python -m deezy encode ddp "C:\\media\\song.wav" --channels 2 --output-template "{title}_{channels}.ddp" --output-preview
````
