# Dolby TrueHD (thd)

Dolby TrueHD, lossless, written as `.thd` (`.mlp` is taken too). Every option is
on [deezy encode thd](../cli/encode-thd.md).

```bash
deezy encode thd movie.mkv
deezy encode thd --channels 8 --drc none movie.mkv
```

## Layouts and sample rate

`--channels` picks 2.0 (`2`), 5.1 (`6`) or 7.1 (`8`). Auto (`0`, the default)
takes the smallest layout that holds every source channel and fills the rest
with silence: a mono source becomes full-level dual mono, and a 5.0 or 7.0
source gets a silent LFE, as does `--disable-lfe`.

DEE encodes 48 or 96 kHz: a source above 48 kHz is encoded at 96 kHz, any other
at 48 kHz.

## Loudness and DRC

DEE measures the loudness and writes the measured dialnorm; `--custom-dialnorm`
writes a set one, and `--loudness-preset` works as for
[Dolby Digital](dd.md#loudness). TrueHD is lossless, so nothing corrects the
audio. `--drc` sets the DRC profile of every presentation in the stream
(`film_light` by default); `none` needs [dee_shim](../dee-shim.md).

## Through dee_shim

When DeeZy finds dee_shim, every thd encode runs through it. At 96 kHz dee_shim
turns off DEE's apodizing filter, so the stream decodes to the source sample for
sample; `--no-as-is` keeps DEE's filter.
