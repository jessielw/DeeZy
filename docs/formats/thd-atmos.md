# Dolby TrueHD with Dolby Atmos (thd-atmos)

Dolby TrueHD with Dolby Atmos, written as `.thd`. Every option is on
[deezy encode thd-atmos](../cli/encode-thd-atmos.md).

```bash
deezy encode thd-atmos master.atmos
deezy encode thd-atmos --atmos-elements 12 movie.mkv
```

## Sources

The source is a TrueHD Atmos track (truehdd decodes it to a DAMF master first, so DeeZy needs truehdd), a DAMF master (the `.atmos` file, beside its `.atmos.metadata` and `.atmos.audio`) or an ADM BWF master (`.wav`). Besides the Atmos presentation, DEE writes 7.1, 5.1
and 2.0 presentations it downmixes from it.

## Elements

`--atmos-elements` (12, 14 or 16, default 16) sets how many elements the stream
codes the master's bed and objects into. More keep more of the master's detail
and make a bigger stream; Dolby's default is 12. A master with more elements
than that is clustered into them, and DeeZy logs why. MediaInfo's bed and object
counts follow the stream's element count.

## Legacy authoring

Off by default (Dolby's default is on). `--legacy-authoring` makes a stream for
older disc-authoring tools; such a stream carries no warp mode.

## Through dee_shim

When DeeZy finds [dee_shim](../dee-shim.md), every thd-atmos encode runs
through it, and a master of no more elements than `--atmos-elements` is coded as
it is, so the stream decodes to it sample for sample. `--no-as-is` keeps DEE's
own processing. `--drc none` needs dee_shim.

## Loudness and DRC

DEE measures the loudness and writes the measured dialnorm; `--custom-dialnorm`
writes a set one and `--loudness-preset` works as for
[Dolby Digital](dd.md#loudness). `--drc` sets every presentation's DRC profile.

## Warp mode

A TrueHD Atmos stream that carries no warp mode reaches DEE with none, which DEE renders as `warping`, its own default. `--thd-warp-mode` gives such a stream one (`normal`, `warping`, `prologiciix` or `loro`). A stream that has a warp mode keeps it. DeeZy 1.x gave every such stream `normal`. The warp mode changes no TrueHD audio, only the flag in the stream.
