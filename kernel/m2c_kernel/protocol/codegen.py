"""Generate TypeScript types from the kernel's wire types.

    python -m m2c_kernel.protocol.codegen            write all files
    python -m m2c_kernel.protocol.codegen --check    fail if any file is out of date
    python -m m2c_kernel.protocol.codegen --module m2c_kernel.commands.fit
                                                     write only that module's file

Every Python module that defines wire types gets exactly one TypeScript file in
`src/shared/protocol/generated/`, so parallel work on different modules never
touches the same generated file:

| Python module                   | TypeScript file              |
|---------------------------------|------------------------------|
| `commands/<group>.py`           | `<group>.ts`                 |
| `features/types/<type>.py`      | `feature-<type>.ts`          |
| `codes/<group>.py`              | `codes-<group>.ts`           |
| `limits.py`, `protocol`         | `limits.ts`, `protocol.ts`   |
| any other module, e.g. `a/b.py` | `a-b.ts`                     |

`index.ts` combines the per-module tables. It lists every command module and
feature type, including those without methods yet, so it only changes when a
module is added or removed.

Fields with defaults are optional in types that the renderer sends. A type that
is both sent and received gets a second `...Input` interface with the optional
fields; the plain interface describes what the kernel returns (all fields set).
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib
import pkgutil
import re
import sys
from collections.abc import Iterable
from enum import Enum
from pathlib import Path
from typing import Any, Literal, TypeAliasType, get_args, get_origin

from m2c_kernel import limits
from m2c_kernel.features.registry import FeatureTypeSpec, load_feature_types
from m2c_kernel.protocol import PROTOCOL_VERSION
from m2c_kernel.protocol.registry import CommandSpec, load_commands
from m2c_kernel.protocol.wire import (
    JsonValue,
    Range,
    RawObject,
    fields_of,
    is_union,
    unwrap,
)

GENERATED_DIR = Path(__file__).resolve().parents[3] / "src" / "shared" / "protocol" / "generated"
_WIRE_MODULE = "m2c_kernel.protocol.wire"
_BUILTIN_ALIASES = {
    "U8Array": "Uint8Array",
    "U16Array": "Uint16Array",
    "U32Array": "Uint32Array",
    "I32Array": "Int32Array",
    "F32Array": "Float32Array",
    "F64Array": "Float64Array",
    "BlobRef": "BlobRef",
    "JsonValue": "JsonValue",
}
_WIRE_TYPES_IMPORT = "../wireTypes"
_NONE = type(None)

type Mode = Literal["input", "output"]


def ts_file_stem(module: str) -> str:
    """TypeScript file name (without extension) for a Python module."""
    relative = module.removeprefix("m2c_kernel.")
    parts = relative.split(".")
    if parts[0] == "commands" and len(parts) == 2:
        return parts[1]
    if parts[:2] == ["features", "types"] and len(parts) == 3:
        return "feature-" + _kebab(parts[2])
    if parts[0] == "codes" and len(parts) == 2:
        return "codes-" + parts[1]
    return "-".join(_kebab(part) for part in parts)


def _kebab(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "-", name).replace("_", "-").lower()


def _pascal(name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in re.split(r"[._-]", name))


def _upper_snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).replace("-", "_").upper()


def _has_own_doc(obj: Any) -> bool:
    doc = getattr(obj, "__doc__", None)
    return isinstance(doc, str) and bool(doc) and not doc.startswith(f"{obj.__name__}(")


def _jsdoc(text: str | None, indent: str = "") -> list[str]:
    if not text:
        return []
    lines = [line.strip() for line in text.strip().splitlines()]
    if len(lines) == 1:
        return [f"{indent}/** {lines[0]} */"]
    return [f"{indent}/**", *[f"{indent} * {line}".rstrip() for line in lines], f"{indent} */"]


class _Model:
    """All wire types reachable from the registries, with the directions they travel in."""

    def __init__(self) -> None:
        self.modes: dict[Any, set[Mode]] = {}

    def visit(self, annotation: Any, mode: Mode) -> None:
        if isinstance(annotation, TypeAliasType):
            if annotation.__module__ == _WIRE_MODULE:
                return
            self._mark(annotation, mode)
            self.visit(annotation.__value__, mode)
            return
        base, _ = unwrap(annotation)
        if base is not annotation:
            self.visit(base, mode)
            return
        if is_union(base) or get_origin(base) in (list, tuple, dict):
            for argument in get_args(base):
                if argument is not Ellipsis:
                    self.visit(argument, mode)
            return
        if isinstance(base, type) and dataclasses.is_dataclass(base) and base is not RawObject:
            if self._mark(base, mode):
                for info in fields_of(base):
                    self.visit(info.annotation, mode)
            return
        if isinstance(base, type) and issubclass(base, Enum):
            self._mark(base, mode)

    def _mark(self, obj: Any, mode: Mode) -> bool:
        seen = self.modes.setdefault(obj, set())
        if mode in seen:
            return False
        seen.add(mode)
        return True

    def needs_input_variant(self, obj: Any) -> bool:
        """Received and sent, and optional fields exist somewhere inside: emit `...Input` too."""
        modes = self.modes.get(obj, set())
        return modes == {"input", "output"} and self._has_defaults(obj, set())

    def _has_defaults(self, obj: Any, seen: set[Any]) -> bool:
        if obj in seen:
            return False
        seen.add(obj)
        if isinstance(obj, TypeAliasType):
            return any(self._has_defaults(item, seen) for item in _referenced_types(obj.__value__))
        if not (isinstance(obj, type) and dataclasses.is_dataclass(obj)):
            return False
        for info in fields_of(obj):
            if info.has_default:
                return True
            if any(
                self._has_defaults(nested, seen) for nested in _referenced_types(info.annotation)
            ):
                return True
        return False


def _referenced_types(annotation: Any) -> Iterable[Any]:
    if isinstance(annotation, TypeAliasType):
        yield annotation
        yield from _referenced_types(annotation.__value__)
        return
    base, _ = unwrap(annotation)
    if base is not annotation:
        yield from _referenced_types(base)
    elif is_union(base) or get_origin(base) in (list, tuple, dict):
        for argument in get_args(base):
            if argument is not Ellipsis:
                yield from _referenced_types(argument)
    elif isinstance(base, type):
        yield base


class _File:
    """One generated TypeScript file."""

    def __init__(self, module: str, model: _Model) -> None:
        self.module = module
        self.stem = ts_file_stem(module)
        self.model = model
        self.imports: dict[str, set[str]] = {}
        self.body: list[str] = []

    def ts(self, annotation: Any, mode: Mode) -> str:
        """TypeScript type expression for an annotation."""
        if isinstance(annotation, TypeAliasType):
            if annotation.__module__ == _WIRE_MODULE:
                name = _BUILTIN_ALIASES[annotation.__name__]
                if name in ("BlobRef", "JsonValue"):
                    self.imports.setdefault(_WIRE_TYPES_IMPORT, set()).add(name)
                return name
            return self._reference(annotation, annotation.__name__, mode)
        base, _ = unwrap(annotation)
        if base is JsonValue:
            self.imports.setdefault(_WIRE_TYPES_IMPORT, set()).add("JsonValue")
            return "JsonValue"
        if base is not annotation:
            return self.ts(base, mode)
        if is_union(base):
            members = [self.ts(argument, mode) for argument in get_args(base)]
            return " | ".join(dict.fromkeys(members))
        origin = get_origin(base)
        if origin is Literal:
            return " | ".join(_literal(value) for value in get_args(base))
        if origin in (list, tuple):
            args = get_args(base)
            if origin is tuple and not (len(args) == 2 and args[1] is Ellipsis):
                return "[" + ", ".join(self.ts(argument, mode) for argument in args) + "]"
            item = self.ts(args[0], mode)
            return f"({item})[]" if " " in item else f"{item}[]"
        if origin is dict:
            return f"Record<string, {self.ts(get_args(base)[1], mode)}>"
        if base is RawObject:
            return "Record<string, unknown>"
        simple = {int: "number", float: "number", str: "string", bool: "boolean", _NONE: "null"}
        if base in simple:
            return simple[base]
        if isinstance(base, type) and (dataclasses.is_dataclass(base) or issubclass(base, Enum)):
            return self._reference(base, base.__name__, mode)
        raise TypeError(f"{self.module}: no TypeScript mapping for {annotation!r}")

    def _reference(self, obj: Any, name: str, mode: Mode) -> str:
        if mode == "input" and self.model.needs_input_variant(obj):
            name = f"{name}Input"
        stem = ts_file_stem(obj.__module__)
        if stem != self.stem:
            self.imports.setdefault(f"./{stem}", set()).add(name)
        return name

    def emit_dataclass(self, cls: type) -> None:
        modes = self.model.modes.get(cls, {"output"})
        if self.model.needs_input_variant(cls):
            self._emit_interface(cls, cls.__name__, optional_defaults=False, mode="output")
            self._emit_interface(cls, f"{cls.__name__}Input", optional_defaults=True, mode="input")
        else:
            is_input = modes == {"input"}
            mode: Mode = "input" if is_input else "output"
            self._emit_interface(cls, cls.__name__, optional_defaults=is_input, mode=mode)
        ranges = {
            info.key: limit
            for info in fields_of(cls)
            for limit in unwrap(info.annotation)[1]
            if isinstance(limit, Range)
        }
        if ranges:
            entries = ", ".join(
                f"{key}: {{ min: {_number(limit.min)}, max: {_number(limit.max)} }}"
                for key, limit in ranges.items()
            )
            self.body += [
                f"export const {_upper_snake(cls.__name__)}_RANGES = {{ {entries} }} as const;",
                "",
            ]

    def _emit_interface(self, cls: type, name: str, optional_defaults: bool, mode: Mode) -> None:
        if name != cls.__name__:
            self.body += _jsdoc(
                f"Input form of `{cls.__name__}`: fields with defaults may be omitted."
            )
        elif _has_own_doc(cls):
            self.body += _jsdoc(cls.__doc__)
        infos = fields_of(cls)
        if not infos:
            self.body += [f"export type {name} = Record<string, never>;", ""]
            return
        self.body.append(f"export interface {name} {{")
        for info in infos:
            # The `type` discriminator of a union member is always sent.
            optional = optional_defaults and info.has_default and info.name != "type"
            marker = "?" if optional else ""
            self.body.append(f"  {info.key}{marker}: {self.ts(info.annotation, mode)};")
        self.body += ["}", ""]

    def emit_alias(self, alias: TypeAliasType) -> None:
        modes = self.model.modes.get(alias, {"output"})
        mode: Mode = "input" if modes == {"input"} else "output"
        self.body += [f"export type {alias.__name__} = {self.ts(alias.__value__, mode)};", ""]
        if self.model.needs_input_variant(alias):
            self.body += [
                f"export type {alias.__name__}Input = {self.ts(alias.__value__, 'input')};",
                "",
            ]

    def emit_enum(self, enum: type[Enum]) -> None:
        values = " | ".join(_literal(member.value) for member in enum)
        self.body += [f"export type {enum.__name__} = {values};", ""]

    def render(self) -> str:
        lines = [_header(self.module), ""]
        for path in sorted(self.imports):
            names = ", ".join(sorted(self.imports[path]))
            lines.append(f"import type {{ {names} }} from '{path}';")
        if self.imports:
            lines.append("")
        while self.body and self.body[-1] == "":
            self.body.pop()
        return "\n".join(lines + self.body) + "\n"


def _header(module: str | None = None) -> str:
    """First line of every generated file, naming its source module."""
    origin = f" from kernel/{module.replace('.', '/')}.py" if module else ""
    return f"// Generated by m2c_kernel.protocol.codegen{origin}. Do not edit."


def _literal(value: object) -> str:
    if isinstance(value, str):
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    if isinstance(value, bool):
        return "true" if value else "false"
    return repr(value)


def _number(value: float | None) -> str:
    if value is None:
        return "null"
    return repr(int(value)) if float(value).is_integer() else repr(value)


def _module_names(package: str) -> list[str]:
    module = importlib.import_module(package)
    return sorted(f"{package}.{info.name}" for info in pkgutil.iter_modules(module.__path__))


def generate() -> dict[str, str]:
    """Return every generated file as {file name: content}."""
    commands = load_commands()
    feature_types = load_feature_types()
    command_modules = _module_names("m2c_kernel.commands")
    feature_modules = _module_names("m2c_kernel.features.types")
    code_modules = _module_names("m2c_kernel.codes")

    model = _Model()
    for spec in commands.values():
        model.visit(spec.params_type, "input")
        model.visit(spec.result_type, "output")
    for feature in feature_types.values():
        model.visit(feature.params_type, "output")
        model.visit(feature.input_type, "input")

    files: dict[str, _File] = {}

    def file_for(module: str) -> _File:
        if module not in files:
            files[module] = _File(module, model)
        return files[module]

    for module in [*command_modules, *feature_modules]:
        file_for(module)
    for obj in sorted(model.modes, key=lambda item: (item.__module__, _definition_order(item))):
        target = file_for(obj.__module__)
        if isinstance(obj, TypeAliasType):
            target.emit_alias(obj)
        elif isinstance(obj, type) and issubclass(obj, Enum):
            target.emit_enum(obj)
        else:
            target.emit_dataclass(obj)

    for module in command_modules:
        _emit_method_table(
            file_for(module), [s for s in commands.values() if _module_of(s) == module]
        )
    for feature in feature_types.values():
        _emit_feature_type(file_for(feature.module), feature)

    output = {f"{target.stem}.ts": target.render() for target in files.values()}
    for module in code_modules:
        output[f"{ts_file_stem(module)}.ts"] = _codes_file(module)
    output["limits.ts"] = _limits_file()
    output["protocol.ts"] = _protocol_file()
    output["index.ts"] = _index_file(command_modules, feature_modules, code_modules, feature_types)
    return dict(sorted(output.items()))


def _definition_order(obj: Any) -> int:
    """Keep the order of definition in the source module (line number)."""
    try:
        import inspect

        return inspect.getsourcelines(obj)[1]
    except (OSError, TypeError):
        return 0


def _module_of(spec: CommandSpec) -> str:
    return spec.handler.__module__


def _emit_method_table(target: _File, specs: list[CommandSpec]) -> None:
    group = target.stem
    interface = f"{_pascal(group)}Methods"
    table = f"{_upper_snake(group)}_METHODS"
    target.imports.setdefault(_WIRE_TYPES_IMPORT, set()).add("MethodInfo")
    if not specs:
        target.body += [
            f"export type {interface} = Record<never, never>;",
            "",
            f"export const {table}: Record<string, MethodInfo> = {{}};",
            "",
        ]
        return
    target.body.append(f"export interface {interface} {{")
    for spec in specs:
        params = target.ts(spec.params_type, "input")
        result = target.ts(spec.result_type, "output")
        target.body.append(f"  '{spec.method}': {{ params: {params}; result: {result} }};")
    target.body += ["}", "", f"export const {table} = {{"]
    for spec in specs:
        lane = "true" if spec.lane else "false"
        exclusive = "true" if spec.exclusive else "false"
        info = f"lane: {lane}, caller: '{spec.caller}', exclusive: {exclusive}"
        target.body.append(f"  '{spec.method}': {{ {info} }},")
    target.body += [f"}} as const satisfies Record<keyof {interface}, MethodInfo>;", ""]


def _emit_feature_type(target: _File, spec: FeatureTypeSpec) -> None:
    params = target.ts(spec.params_type, "output")
    feature_input = target.ts(spec.input_type, "input")
    target.body += [
        f"export interface {_pascal(spec.type_id)}FeatureType {{",
        f"  type: '{spec.type_id}';",
        f"  params: {params};",
        f"  input: {feature_input};",
        "}",
        "",
    ]


def _codes_file(module: str) -> str:
    imported = importlib.import_module(module)
    group = module.rsplit(".", 1)[-1]
    prefix = _upper_snake(group)
    lines = [_header(module), ""]
    for enum_name, suffix, type_suffix in (
        ("ErrorCode", "ERROR_CODES", "ErrorCode"),
        ("IssueCode", "ISSUE_CODES", "IssueCode"),
        ("ProgressStage", "PROGRESS_STAGES", "ProgressStage"),
    ):
        enum = getattr(imported, enum_name, None)
        values = [member.value for member in enum] if enum is not None else []
        items = "".join(f"\n  {_literal(value)}," for value in values)
        closing = "\n" if values else ""
        lines += [
            f"export const {prefix}_{suffix} = [{items}{closing}] as const;",
            f"export type {_pascal(group)}{type_suffix} = (typeof {prefix}_{suffix})[number];",
            "",
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _limits_file() -> str:
    lines = [_header("m2c_kernel.limits"), ""]
    for name, value in vars(limits).items():
        if name.isupper() and isinstance(value, int | float) and not isinstance(value, bool):
            lines.append(f"export const {name} = {_number(value)};")
    return "\n".join(lines) + "\n"


def _protocol_file() -> str:
    header = _header("m2c_kernel.protocol.__init__")
    return f"{header}\n\nexport const PROTOCOL_VERSION = {PROTOCOL_VERSION};\n"


def _index_file(
    command_modules: list[str],
    feature_modules: list[str],
    code_modules: list[str],
    feature_types: dict[str, FeatureTypeSpec] | Any,
) -> str:
    lines = [_header(), ""]
    method_types, tables = [], []
    for module in command_modules:
        stem = ts_file_stem(module)
        interface, table = f"{_pascal(stem)}Methods", f"{_upper_snake(stem)}_METHODS"
        lines.append(f"import {{ type {interface}, {table} }} from './{stem}';")
        method_types.append(interface)
        tables.append(table)
    code_lists: dict[str, list[str]] = {"ERROR_CODES": [], "ISSUE_CODES": [], "PROGRESS_STAGES": []}
    for module in code_modules:
        stem = ts_file_stem(module)
        prefix = _upper_snake(module.rsplit(".", 1)[-1])
        names = [f"{prefix}_{suffix}" for suffix in code_lists]
        for suffix, name in zip(code_lists, names, strict=True):
            code_lists[suffix].append(name)
        lines.append(f"import {{ {', '.join(names)} }} from './{stem}';")
    by_module = {spec.module: spec for spec in feature_types.values()}
    feature_entries = []
    for module in feature_modules:
        spec = by_module.get(module)
        if spec is None:
            continue
        name = f"{_pascal(spec.type_id)}FeatureType"
        lines.append(f"import type {{ {name} }} from './{ts_file_stem(module)}';")
        feature_entries.append((spec.type_id, name))
    lines += ["", f"export type KernelMethods = {' & '.join(method_types)};", ""]
    lines.append("export const METHOD_TABLE = {")
    lines += [f"  ...{table}," for table in tables]
    lines += ["};", "", "export type MethodName = keyof KernelMethods;", ""]
    for suffix, names in code_lists.items():
        lines.append(f"export const {suffix}: readonly string[] = [")
        lines += [f"  ...{name}," for name in names]
        lines += ["];", ""]
    lines.append("export interface FeatureTypes {")
    lines += [f"  {type_id}: {name};" for type_id, name in feature_entries]
    lines += ["}", "", "export type FeatureTypeId = keyof FeatureTypes;", ""]
    lines.append("export const FEATURE_TYPE_IDS = [")
    lines += [f"  '{type_id}'," for type_id, _ in feature_entries]
    lines += ["] as const satisfies readonly FeatureTypeId[];"]
    return "\n".join(lines) + "\n"


def module_for_file(file_name: str, modules: Iterable[str]) -> str | None:
    for module in modules:
        if f"{ts_file_stem(module)}.ts" == file_name:
            return module
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--check", action="store_true", help="fail if generated files are stale")
    parser.add_argument("--module", help="write only the file of this Python module")
    parser.add_argument("--out", type=Path, default=GENERATED_DIR, help="output directory")
    args = parser.parse_args(argv)

    files = generate()
    out: Path = args.out
    if args.module:
        wanted = f"{ts_file_stem(args.module)}.ts"
        if wanted not in files:
            print(f"no generated file for module {args.module}", file=sys.stderr)
            return 2
        files = {wanted: files[wanted]}

    if args.check:
        stale = [name for name, text in files.items() if _read(out / name) != text]
        if not args.module:
            known = set(files)
            stale += sorted(path.name for path in out.glob("*.ts") if path.name not in known)
        if stale:
            print("generated files are out of date: " + ", ".join(stale), file=sys.stderr)
            print("run: npm run codegen", file=sys.stderr)
            return 1
        return 0

    out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        if _read(out / name) != text:
            (out / name).write_text(text, encoding="utf-8", newline="\n")
    if not args.module:
        for path in out.glob("*.ts"):
            if path.name not in files:
                path.unlink()
    return 0


def _read(path: Path) -> str | None:
    return path.read_text(encoding="utf-8") if path.exists() else None


if __name__ == "__main__":
    sys.exit(main())
