"""Document operations applied by `doc.apply` and evaluated by `doc.preview`.

Several operations in one request form one revision. Feature parameters arrive
as a `RawObject`: the feature type decodes them with its input type and turns
arrays into blobs (`store`), so the document only ever holds JSON and blob
references.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from m2c_kernel.codes.document import ErrorCode
from m2c_kernel.document.model import (
    Alignment,
    AlignmentAdjust,
    Document,
    DocumentSettings,
    Feature,
)
from m2c_kernel.features.registry import FeatureTypeSpec
from m2c_kernel.limits import MAX_FEATURES
from m2c_kernel.protocol.errors import KernelError
from m2c_kernel.protocol.wire import JsonValue, RawObject, from_json, from_wire, to_json
from m2c_kernel.session.blobs import BlobStore


@dataclass(frozen=True, kw_only=True)
class NewFeature:
    type: str
    name: str | None = None
    params: RawObject


@dataclass(frozen=True, kw_only=True)
class AddFeature:
    type: Literal["addFeature"] = "addFeature"
    feature: NewFeature


@dataclass(frozen=True, kw_only=True)
class UpdateFeature:
    type: Literal["updateFeature"] = "updateFeature"
    id: str
    params: RawObject


@dataclass(frozen=True, kw_only=True)
class RenameFeature:
    type: Literal["renameFeature"] = "renameFeature"
    id: str
    name: str | None


@dataclass(frozen=True, kw_only=True)
class DeleteFeature:
    type: Literal["deleteFeature"] = "deleteFeature"
    id: str
    cascade: bool = False


@dataclass(frozen=True, kw_only=True)
class SetSuppressed:
    type: Literal["setSuppressed"] = "setSuppressed"
    id: str
    suppressed: bool


@dataclass(frozen=True, kw_only=True)
class SetAlignment:
    type: Literal["setAlignment"] = "setAlignment"
    method: Literal["none", "auto", "faces"]
    params: JsonValue = None
    adjust: AlignmentAdjust = field(default_factory=AlignmentAdjust)


@dataclass(frozen=True, kw_only=True)
class SetSettings:
    type: Literal["setSettings"] = "setSettings"
    settings: DocumentSettings


type DocOp = (
    AddFeature
    | UpdateFeature
    | RenameFeature
    | DeleteFeature
    | SetSuppressed
    | SetAlignment
    | SetSettings
)


@dataclass(frozen=True)
class AppliedOps:
    document: Document
    touched: tuple[str, ...]
    """Ids of added or changed features, in history order (previews evaluate up to the last)."""


def apply_ops(
    document: Document,
    ops: Sequence[DocOp],
    feature_types: Mapping[str, FeatureTypeSpec],
    blobs: BlobStore,
) -> AppliedOps:
    touched: list[str] = []
    for op in ops:
        match op:
            case AddFeature(feature=new):
                document, feature_id = _add(document, new, feature_types, blobs)
                touched.append(feature_id)
            case UpdateFeature(id=feature_id, params=params):
                document = _update(document, feature_id, params, feature_types, blobs)
                touched.append(feature_id)
            case RenameFeature(id=feature_id, name=name):
                document = _replace_feature(document, feature_id, name=name)
            case DeleteFeature(id=feature_id, cascade=cascade):
                document = _delete(document, feature_id, cascade, feature_types)
            case SetSuppressed(id=feature_id, suppressed=suppressed):
                document = _replace_feature(document, feature_id, suppressed=suppressed)
                touched.append(feature_id)
            case SetAlignment(method=method, params=params, adjust=adjust):
                alignment = Alignment(method=method, params=params, adjust=adjust)
                document = replace(document, alignment=alignment)
            case SetSettings(settings=settings):
                document = replace(document, settings=settings)
    order = {feature.id: index for index, feature in enumerate(document.features)}
    touched = sorted({item for item in touched if item in order}, key=order.__getitem__)
    return AppliedOps(document, tuple(touched))


def dependents(
    document: Document, feature_id: str, feature_types: Mapping[str, FeatureTypeSpec]
) -> list[str]:
    """Features that reference `feature_id` directly or indirectly, in history order."""
    affected = {feature_id}
    result: list[str] = []
    for feature in document.features:
        if feature.id in affected:
            continue
        refs = _references(feature, feature_types)
        if affected.intersection(refs):
            affected.add(feature.id)
            result.append(feature.id)
    return result


def _spec(feature_types: Mapping[str, FeatureTypeSpec], type_id: str) -> FeatureTypeSpec:
    spec = feature_types.get(type_id)
    if spec is None:
        raise KernelError(ErrorCode.UNKNOWN_FEATURE_TYPE, {"type": type_id})
    return spec


def _stored_params(spec: FeatureTypeSpec, raw: RawObject, blobs: BlobStore) -> JsonValue:
    decoded: Any = from_wire(raw.json, spec.input_type, raw.buffers)
    stored = spec.store(decoded, blobs)
    result: JsonValue = to_json(stored, spec.params_type)
    return result


def _references(feature: Feature, feature_types: Mapping[str, FeatureTypeSpec]) -> set[str]:
    spec = feature_types.get(feature.type)
    if spec is None:
        return set()
    refs = spec.references(from_json(feature.params, spec.params_type))
    return {*refs.features, *refs.bodies}


def _check_references(document: Document, index: int, refs: set[str], feature_id: str) -> None:
    earlier = {feature.id for feature in document.features[:index]}
    for ref in refs:
        if ref not in earlier:
            code = (
                ErrorCode.FORWARD_REFERENCE if document.feature(ref) else ErrorCode.UNKNOWN_FEATURE
            )
            raise KernelError(code, {"feature": feature_id, "reference": ref})


def _add(
    document: Document,
    new: NewFeature,
    feature_types: Mapping[str, FeatureTypeSpec],
    blobs: BlobStore,
) -> tuple[Document, str]:
    if len(document.features) >= MAX_FEATURES:
        raise KernelError(ErrorCode.LIMIT_EXCEEDED, {"limit": MAX_FEATURES})
    spec = _spec(feature_types, new.type)
    feature_id = f"f{document.next_id}"
    feature = Feature(
        id=feature_id,
        type=new.type,
        name=new.name,
        suppressed=False,
        params=_stored_params(spec, new.params, blobs),
    )
    _check_references(
        document, len(document.features), _references(feature, feature_types), feature_id
    )
    return (
        replace(document, features=(*document.features, feature), next_id=document.next_id + 1),
        feature_id,
    )


def _update(
    document: Document,
    feature_id: str,
    params: RawObject,
    feature_types: Mapping[str, FeatureTypeSpec],
    blobs: BlobStore,
) -> Document:
    index, feature = _find(document, feature_id)
    spec = _spec(feature_types, feature.type)
    updated = replace(feature, params=_stored_params(spec, params, blobs))
    _check_references(document, index, _references(updated, feature_types), feature_id)
    features = list(document.features)
    features[index] = updated
    return replace(document, features=tuple(features))


def _delete(
    document: Document,
    feature_id: str,
    cascade: bool,
    feature_types: Mapping[str, FeatureTypeSpec],
) -> Document:
    _find(document, feature_id)
    users = dependents(document, feature_id, feature_types)
    if users and not cascade:
        raise KernelError(ErrorCode.HAS_DEPENDENTS, {"feature": feature_id, "count": len(users)})
    removed = {feature_id, *users}
    return replace(
        document, features=tuple(item for item in document.features if item.id not in removed)
    )


def _replace_feature(document: Document, feature_id: str, **changes: object) -> Document:
    index, feature = _find(document, feature_id)
    features = list(document.features)
    features[index] = replace(feature, **changes)  # type: ignore[arg-type]
    return replace(document, features=tuple(features))


def _find(document: Document, feature_id: str) -> tuple[int, Feature]:
    for index, feature in enumerate(document.features):
        if feature.id == feature_id:
            return index, feature
    raise KernelError(ErrorCode.UNKNOWN_FEATURE, {"feature": feature_id})
