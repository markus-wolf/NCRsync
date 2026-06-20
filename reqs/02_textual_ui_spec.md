# 02 - Textual UI Specification

## 1. Framework

The UI shall be implemented using **Textual**.

```bash
pip install textual
```

Optional development extras:

```bash
pip install textual-dev
```

## 2. Main Layout

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ NCRsync | Host: 80078 | Remote: /downloads/tv | Local: ~/Downloads           │
├──────────────────────────────────────┬───────────────────────────────────────┤
│ RemotePane                           │ LocalPane                             │
│ /downloads/tv                        │ /Users/alex/Downloads                 │
│                                      │                                       │
│ > [D] The.Show.S03                   │   file1.mkv                           │
│   The.Show.S03E01.mkv                │   file2.mkv                           │
│   The.Show.S03E02.mkv                │                                       │
├──────────────────────────────────────┴───────────────────────────────────────┤
│ QueuePane: 2 queued, 0 running, 0 failed                                     │
├──────────────────────────────────────────────────────────────────────────────┤
│ TransferLog                                                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│ : command input                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ F3 View  F5 Copy  F6 Queue  F8 Remove  F9 Menu  F10 Quit                     │
└──────────────────────────────────────────────────────────────────────────────┘
```

## 3. Textual Widgets

| UI Area | Textual Widget |
|---|---|
| Header | `Header` |
| Footer | `Footer` |
| Remote pane | `DataTable` or `ListView` |
| Local pane | `DataTable` or `ListView` |
| Queue pane | `DataTable` |
| Transfer log | `Log` or `RichLog` |
| Command input | `Input` |
| Progress | `ProgressBar` |
| Dialogs | `ModalScreen` |

## 4. Key Bindings

```python
BINDINGS = [
    ("tab", "switch_pane", "Switch Pane"),
    ("f5", "copy", "Copy"),
    ("f6", "queue", "Queue"),
    ("f8", "remove", "Remove"),
    ("f10", "quit", "Quit"),
    ("ctrl+r", "refresh", "Refresh"),
    ("space", "toggle_select", "Select"),
    ("backspace", "parent_dir", "Parent"),
]
```

## 5. Pane Behavior

Remote pane shows entries sorted directories-first, current row highlighted, selected rows marked, Enter on directory changes remote cwd, and Space toggles selection.

Local pane has the same navigation behavior and sets the transfer destination.

## 6. Command Input

Commands: `cd DIR`, `lcd DIR`, `ls`, `ll`, `select PATTERN`, `queue`, `download`, `doctor`, `clear`, `quit`.

Command history should support arrow-up/down.

## 7. Transfer UI

During transfer, show active filename, file progress, total queue progress, transfer rate, ETA if parseable, and raw rsync output.

## 8. Themes

Provide a modern dark theme and an NC blue theme.

## 9. Responsiveness

All remote commands and rsync processes shall run asynchronously or in worker threads. The UI must not freeze during remote listing, rsync transfer, or diagnostics.
