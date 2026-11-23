# Delay

!!!question "How is delay handled?"

- If delay is detected inside a container _(mkv, mp4, etc and it includes a video track)_ there can be a **delay relative to source** field. DeeZy will utilize this to automatically detect and strip the delay to **0** for the output.
- If there is a delay string in the **filename**, it will strip the delay to **0** for the output.
- CLI argument `--delay=10ms` overrides all above detection if utilized. It
  takes milliseconds or seconds, decimals allowed, or frames at a frame rate:
  `--delay=-10.5ms`, `--delay=1.25s`, `--delay=-3@23.976` (the rate may also be
  `24000/1001`, `ntsc`, `pal`, `film` or `ntsc-film`). The `=` is required for a
  negative value.
  - If provided it will pad/trim **Nms** from the file to essentially set it to **0**.

!!!question "When does delay stripping take place?"

DeeZy feeds the appropriate parameters to DEE during **encoding** to strip the delay.

!!!question "What happens to the delay string in my filename?"

If DeeZy strips the delay it will output **DELAY 0ms** to the output file name _(if automatically generating the filename)_.

!!!notes

- Filename modifications will only happen for **automatically** generated names via the template or by the user providing no output. Filename modifications will **not** happen if a user explicitly sets the filename.
- Delay detection is always ran.
- Priority is **CLI** > **container** > **filename**.
