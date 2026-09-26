from __future__ import annotations

from pathlib import Path

from m2c_kernel.features.registry import load_feature_types
from m2c_kernel.protocol.codegen import GENERATED_DIR, generate, main, ts_file_stem
from m2c_kernel.protocol.registry import load_commands


def test_generation_is_deterministic() -> None:
    assert generate() == generate()


def test_generated_files_in_the_repository_are_current() -> None:
    assert main(["--check", "--out", str(GENERATED_DIR)]) == 0


def test_every_command_group_and_feature_type_has_a_file() -> None:
    files = generate()
    for spec in load_commands().values():
        assert f"{spec.group}.ts" in files
        assert f"'{spec.method}'" in files[f"{spec.group}.ts"]
    index = files["index.ts"]
    for type_id, spec in load_feature_types().items():
        assert f"{ts_file_stem(spec.module)}.ts" in files
        assert f"  {type_id}: " in index


def test_writing_one_module_touches_only_its_file(tmp_path: Path) -> None:
    assert main(["--module", "m2c_kernel.commands.mesh", "--out", str(tmp_path)]) == 0
    assert sorted(path.name for path in tmp_path.iterdir()) == ["mesh.ts"]


def test_file_names_follow_the_module_path() -> None:
    assert ts_file_stem("m2c_kernel.commands.fit") == "fit"
    assert ts_file_stem("m2c_kernel.features.types.primitive_body") == "feature-primitive-body"
    assert ts_file_stem("m2c_kernel.codes.mesh") == "codes-mesh"
    assert ts_file_stem("m2c_kernel.document.model") == "document-model"
