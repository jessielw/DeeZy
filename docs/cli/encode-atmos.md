````markdown
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
```

## Examples

- Encode a single file to Atmos (streaming mode):

```powershell
uv run python -m deezy encode atmos "C:\\media\\scene.wav" --atmos-mode streaming --bitrate 448
```

- Bluray Atmos with bed conformance and preview template:

```powershell
uv run python -m deezy encode atmos "C:\\media\\disc_track.wav" --atmos-mode bluray --bed-conform --output-preview
```

````
