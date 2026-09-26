# Changelog fragments

Pull requests do not edit `CHANGELOG.md` directly, so that parallel branches never conflict.
Instead, each pull request with a user-visible change adds one file to this folder, named after
its branch topic (`changes/sketch-snapping.md`).

A fragment lists its entries under the Keep a Changelog headings that apply:

```markdown
### Added

- Sketch entities snap to design values; each snap can be removed.

### Fixed

- The import panel no longer loses the chosen unit when the file is dropped twice.
```

When a version is released, the fragments are merged into `CHANGELOG.md` and deleted.
