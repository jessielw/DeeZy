# dee_shim

[dee_shim](https://github.com/truehdd/dee-shim) is an optional tool that runs DEE's encoders with options
they don't offer on their own. DeeZy works without it, but some encodes need it,
and DeeZy runs others through it when it is there. DeeZy's executables don't
include it.

## What needs it

| Encode | Without dee_shim |
|---|---|
| `ddp` 7.1 or 7.0 (`--channels 8`, or a 7.0 source) | `--channels 8` is refused; auto picks 5.1, a 7.0 source becomes 5.0 |
| `ddp-bluray` from a 7.0 source | coded as 7.1 with a silent LFE |
| `ddp-atmos --atmos-mode standard` or `bluray` | refused |
| `--bitrate R0:R1` for two-substream DD+ or DD+ Atmos | refused |
| `ddp-atmos --no-surround-90-deg-phase-shift` | refused |
| `thd` or `thd-atmos` with `--drc none` | refused |
| `thd --layout 5.1.2` | refused |
| `deezy measure` of a 7.1 or 7-channel source | refused |

## What runs through it

When DeeZy finds dee_shim, every `ddp-atmos`, `thd` and `thd-atmos` encode runs
through it. On AMD Zen CPUs these encodes run several times faster. The output
changes in three places, each with an option that keeps plain DEE's:

- `ddp-atmos` codes the master's object metadata as it is, where DEE would smooth
  it. `--no-oamd-as-is` keeps DEE's smoothing.
- `thd` at 96 kHz has no apodizing filter, so it decodes to the source sample for
  sample. `--no-as-is` keeps the filter.
- `thd-atmos` codes a master of no more elements than `--atmos-elements` as it
  is, so it decodes to it sample for sample. `--no-as-is` keeps DEE's processing.

Channel-based DD+ uses dee_shim for 7.0, standard 7.1, and Blu-ray 7.1 with
a split bitrate. `deezy measure` uses it only for 7.1:
DEE's meter has 7.1, but its command line takes 1.0, 2.0 and 5.1 only.

## How DeeZy finds it

DeeZy needs dee_shim 0.3.0 or newer. It takes, in order:

1. `--dee-shim PATH`;
2. `dee_shim` in the config's `[dependencies]`;
3. `dee_shim` beside the DEE tools;
4. `apps/dee_shim/` beside DeeZy;
5. `dee_shim` on PATH.

An older dee_shim that DeeZy finds is skipped; an older one you give fails the
encode. `--no-shim`, or `no_shim = true` in the config's `[global_defaults]`,
turns dee_shim off. `deezy tools` shows the dee_shim DeeZy would use.
