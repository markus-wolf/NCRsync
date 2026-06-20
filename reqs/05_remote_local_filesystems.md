# 05 - Remote and Local Filesystem Model

## 1. FileEntry Model

```python
@dataclass
class FileEntry:
    name: str
    path: str
    kind: Literal["file", "dir", "symlink", "other"]
    size: int | None
    mtime: datetime | None
    permissions: str | None
    selected: bool = False
```

## 2. Remote Listing

Preferred Linux command:

```bash
find . -maxdepth 1 -mindepth 1 -printf '%y	%s	%TY-%Tm-%Td %TH:%TM:%TS	%M	%f
'
```

Parse: type, size, mtime, permissions, name.

## 3. Remote Fallback

If GNU find is unavailable, use `ls -la`, remote Python if installed, or an SFTP backend in a later version.

## 4. Local Listing

Use Python standard library: `pathlib.Path.iterdir()` and `stat()`.

## 5. Sorting

Default sort: directories first, files second, others last, alphabetical case-insensitive.

Future sort modes: size, mtime, extension.

## 6. Hidden Files

Configurable:

```toml
show_hidden = true
```

## 7. Selection Model

Selection should be stored as absolute paths, not row indexes. This prevents selection corruption after refresh/sort.

## 8. Bookmarks

Future support for frequently used remote and local paths.

## 9. Dangerous Operations

Delete and overwrite require confirmation. Remote delete is out of scope for early v1 unless explicitly enabled.
