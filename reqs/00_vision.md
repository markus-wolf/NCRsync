# 00 - Vision

## Product Name

Working name: **NCRsync**

## One-line Description

A Norton Commander-style terminal file manager for remote SSH systems, with rsync-powered reliable transfers.

## Core Idea

NCRsync is not merely an rsync wrapper. It is a keyboard-first, dual-pane terminal file manager where one pane may represent a remote SSH host, one pane may represent the local filesystem, and transfer execution uses rsync for reliability and resume support.

## Primary Use Case

A user on a Mac is connected over an unreliable cellular link and wants to download large video files from a home server.

The user should be able to connect, browse remote directories, browse local destination directories, select files, add files to a queue, start transfer, survive disconnects, resume partial downloads, and inspect logs if anything fails.

## Design Philosophy

- Keyboard-first
- Terminal-native
- No server-side agent
- Rsync for transfers
- SSH for remote access
- State should survive crashes
- Errors should be visible and recoverable
- The UI should be pleasant enough for daily use

## Why Textual

Textual is chosen instead of raw curses because it provides high-level widgets, async subprocess support, layout management, keyboard bindings, optional mouse support, CSS-like styling, and clean separation of UI and logic.

This is especially important because rsync transfers should run while the UI remains responsive.
