"""Translatable codes, one module per domain.

Each module defines up to three string enums:

- `ErrorCode`: failures (`KernelError`), i18n namespace `errors`
- `IssueCode`: warnings attached to features or results, namespace `issues`
- `ProgressStage`: labels of progress events, namespace `progress`

Values have the form `<group>.<camelCase>`, where `<group>` is the module name.
Codegen exports them to `src/shared/protocol/generated/codes-<group>.ts`, and a
renderer test checks that German and English translate every value.
"""
