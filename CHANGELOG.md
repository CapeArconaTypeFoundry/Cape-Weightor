# Changelog
All notable changes to this project will be documented in this file.

## [v1.100] - 2026-05-25
### Added
- **Preserve outer width (grow inward)** — scales the outline back into its original horizontal bounding box after the offset, keeping the left and right outer edges pinned and letting the added weight grow inward only. Pairs with *Preserve glyph height* to lock the complete bounding box. *Adjust sidebearings* is automatically disabled while this option is active.
- New preference key `preserveWidth` included in Copy / Paste Parameters.

## [v1.001] - 2026-05-19
### Added
- Adjust sidebearing on/off
### Fixed
- Prevent re-execution if script is still active
