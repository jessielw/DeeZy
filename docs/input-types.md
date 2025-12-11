# Input Types & Patterns

Multiple files and glob patterns are supported.

!!!important

    Use **quotes** if paths contain spaces

    **Example:** _**"**/some_path/sub path/example.mkv**"**_

## Examples

### Single Input

```bash
deezy encode ddp "/media/input one.mkv"
```

### Multiple Input

```bash
deezy encode ddp input1.mkv "/media/input 2.mp4" input3.aac
```

### Glob Patterns

##### Recursive Input (Single Folder)

Iterate a single folder for **mkv** files.

```bash
deezy encode dd "/media/path one/*.mkv"
```

##### Recursive Input (Multiple Folders)

Iterate multiple folders for **aac** files.

```bash
deezy encode dd "/media/path two/**/*.aac"

```

##### Recursive Input (Multiple Folders Advanced)

Iterate two different directories for media files files.

```bash
deezy encode dd "/media/path two/**/*.aac" "/media/path three/**/*.mkv"

```
