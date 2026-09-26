# Changelog

All notable changes to this project are documented in this file. The format is based on
[Keep a Changelog 1.1](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Pull requests add fragments to [changes/](changes/),
which are merged here when a version is released.

## [Unreleased]

### Added

- Project skeleton: Electron main process with a hardened renderer, preload bridge and kernel
  process management; Python geometry kernel with a binary protocol, command registry, document
  model, revisions and rebuild engine; generated TypeScript protocol types.
- Application shell with stages, tool row, project tree, properties panel, status bar, German and
  English user interface, dark and light theme.
- Scan import (STL, OBJ, PLY) with unit choice, display in the 3D viewport, standard views and
  undo.
- Architecture and design specifications, continuous integration and contribution guidelines.
