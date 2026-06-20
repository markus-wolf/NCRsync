# NCRsync Textual Specification Package

NCRsync is a Norton Commander / Midnight Commander inspired terminal file manager for remote SSH hosts, optimized for reliable large-file downloads using `rsync`.

This version of the design explicitly uses **Textual** as the primary UI framework.

## Core Concept

```text
Dual-pane terminal file manager
+ SSH remote browsing
+ local file browser
+ rsync transfer queue
+ resumable downloads
+ persistent logs/state
```

## Documents

1. `00_vision.md`
2. `01_product_requirements.md`
3. `02_textual_ui_spec.md`
4. `03_architecture.md`
5. `04_transfer_engine.md`
6. `05_remote_local_filesystems.md`
7. `06_config_logging_state.md`
8. `07_implementation_roadmap.md`
9. `08_textual_prototype_plan.md`

## Primary Target

- macOS client
- Linux remote host over SSH
- Homebrew rsync 3.x
- Python 3.11+
- Textual
