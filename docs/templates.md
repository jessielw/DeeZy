# Output Filename Templates

Use `--output-template` to generate consistent output filenames when `--output` is not provided.

Example

```
deezy encode ddp --output-template "{title}_{year}_{stem}_{channels}_{delay}" input.mkv
```

Supported tokens: `{title}`, `{year}`, `{stem}`, `{stem-cleaned}`, `{source}`, `{lang}`, `{channels}`, `{worker}`, `{delay}`, `{opt-delay}`

_`opt-delay` will return nothing if delay is equal to 0._

Use `--output-preview` to render a template without running the job.

## `{stem}` token

Automatically removes any type of **DELAY Nms/s** from the filename when used.

**Example Input:**
`Migration Some Random Stuff DELAY 1006ms.flac`

**Example Command:**
`deezy encode dd --output-template "{stem} {opt-delay}"`

**Example Output:**
`Migration Some Random Stuff.ac3`

## `{stem-cleaned}` token

The `{stem-cleaned}` token is a cleaned version of the input file stem and is useful when you want a tidy, human-readable piece of the original filename without common metadata. The cleaner performs the following steps (in roughly this order):

- Remove bracketed or parenthesized tags (e.g. `[eng]`, `(jpn)`).
- Strip explicit delay tokens such as `DELAY 12ms` or `delay-5ms`.
- Remove numeric audio channel annotations such as `5.1`, `2.0`, `7.1ch`, and `5ch`.
- Remove simple channel words commonly used as metadata: `stereo`, `mono`, `dual mono`.
- Remove common codec and sample-rate tokens (e.g. `ac3`, `eac3`, `flac`, `48kHz`, `96k`) so they don't pollute titles.
- Normalize separators (underscores, dots) into spaces and collapse repeated separators/whitespace.

Notes:

- `{stem}` is ignored if `{stem-cleaned}` is used in the same template.
- Leading numeric track numbers are preserved; this keeps filenames like `01` or `03 - Something` meaningful when the numeric portion is the only useful label.

Examples (input stem -> `{stem-cleaned}`):

- `01 - Main Title [eng] DELAY 12ms.eac3` -> `01 Main Title`
- `Track_03 (eng) 48kHz 5.1.flac` -> `Track 03`
- `07 - Surround Mix [eng] 7.1ch.dts` -> `07 Surround Mix`
- `03 - Multichannel [eng] 5ch.eac3` -> `03 Multichannel`
