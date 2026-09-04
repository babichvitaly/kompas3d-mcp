"""Document-scoped topology selection, native feature lifecycle and edge treatments."""

from .advanced_models import DefinitionCall, EdgeTreatment, FeatureSettings
from .backend import require
from .bridge import check_result, invoke, resolve


def _solid_topology(k, document_id, kind):
    import pythoncom

    bodies = k.document(document_id).GetPart(-1).BodyCollection()
    objects = []
    seen = []
    for index in range(bodies.GetCount()):
        body = bodies.GetByIndex(index)
        if not body.IsSolid():
            continue
        faces = body.FaceCollection()
        for fi in range(faces.GetCount()):
            face = faces.GetByIndex(fi)
            definitions = [face]
            if kind == "o3d_edge":
                edges = face.EdgeCollection()
                definitions = [edges.GetByIndex(ei) for ei in range(edges.GetCount())]
            for definition in definitions:
                entity = definition.GetEntity()
                identity = entity._oleobj_.QueryInterface(pythoncom.IID_IUnknown)
                if identity not in seen:
                    seen.append(identity)
                    objects.append(entity)
    return objects


def entities(k, document_id, kind="o3d_unknown", offset=0, limit=100, solid_only=True):
    if offset < 0 or not 1 <= limit <= 500:
        raise ValueError("offset >= 0 and limit 1..500 required")
    if kind not in k.constants or not kind.startswith("o3d_"):
        raise ValueError("Use an installed o3d_ constant")
    if solid_only and kind in {"o3d_edge", "o3d_face"}:
        objects = _solid_topology(k, document_id, kind)
        count = len(objects)
        get_object = objects.__getitem__
    else:
        collection = k.document(document_id).GetPart(-1).EntityCollection(k.constants[kind])
        count = collection.GetCount()
        get_object = collection.GetByIndex
    items = []
    for index in range(offset, min(offset + limit, count)):
        obj = get_object(index)
        item = {
            "entity_id": k.remember(document_id, obj),
            "name": obj.name,
            "type": obj.type,
            "excluded": obj.excluded,
            "hidden": obj.hidden,
            "object": k.pack(obj),
        }
        definition = obj.GetDefinition()
        item["definition"] = k.pack(definition)
        if kind == "o3d_edge":
            curve = definition.GetCurve3D()
            item["geometry"] = {
                "length_mm": definition.GetLength(1),
                "bounds_raw": list(curve.GetGabarit()),
                "straight": bool(definition.IsStraight()),
                "circle": bool(definition.IsCircle()),
                "start_raw": list(curve.GetPoint(curve.GetParamMin())),
                "end_raw": list(curve.GetPoint(curve.GetParamMax())),
            }
        elif kind == "o3d_face":
            item["geometry"] = {
                "area_mm2": definition.GetArea(1),
                "planar": bool(definition.IsPlanar()),
                "cylindrical": bool(definition.IsCylinder()),
            }
            if definition.IsCylinder():
                item["geometry"]["cylinder_raw"] = list(definition.GetCylinderParam())
            edges = definition.EdgeCollection()
            boxes = [edges.GetByIndex(i).GetCurve3D().GetGabarit() for i in range(edges.GetCount())]
            boxes = [box for box in boxes if box[0]]
            if boxes:
                item["geometry"]["bounds_raw"] = (
                    [True]
                    + [min(box[i] for box in boxes) for i in range(1, 4)]
                    + [max(box[i] for box in boxes) for i in range(4, 7)]
                )
        items.append(item)
    return {"document_id": document_id, "total": count, "offset": offset, "entities": items}


def configure(k, document_id, definition, settings: FeatureSettings):
    # Validate references/properties before applying any properties.
    from .bridge import describe_type

    info = describe_type(type(definition))
    values = {
        name: resolve(k, value, document_id=document_id)
        for name, value in settings.properties.items()
    }
    unknown = values.keys() - set(info["writable"])
    if unknown:
        raise ValueError(f"Unknown definition properties: {sorted(unknown)}")
    for name, value in values.items():
        invoke(k, definition, name, "set", [], value)
    for call in settings.calls:
        target = definition
        for getter in call.via:
            target = require(invoke(k, target, getter, "call", [], None), getter)
        value = invoke(
            k,
            target,
            call.member,
            "call",
            resolve(k, call.arguments, document_id=document_id),
            None,
        )
        check_result(value, call.expect)


def create(k, document_id, entity_type, name, settings: FeatureSettings):
    if entity_type not in k.constants or not entity_type.startswith("o3d_"):
        raise ValueError(
            "Expected installed o3d_ type; use api_constants and sdk_read(obj3dtype.html)"
        )
    part = k.document(document_id).GetPart(-1)
    obj = require(part.NewEntity(k.constants[entity_type]), "allocate native feature")
    obj.name = name
    definition = require(obj.GetDefinition(), "get feature definition")
    configure(k, document_id, definition, settings)
    token = k.remember(document_id, obj)
    try:
        require(obj.Create(), "create native feature")
    except Exception as exc:
        raise RuntimeError(f"Feature {token} failed: {exc}. Inspect before retrying.") from exc
    return {
        "feature_id": token,
        "object": k.pack(obj),
        "definition": k.pack(definition),
        "measurements": k.measure(document_id),
    }


def update(k, document_id, entity_id, settings: FeatureSettings):
    obj = k.entity(document_id, entity_id)
    configure(k, document_id, obj.GetDefinition(), settings)
    require(obj.Update(), "update native feature")
    require(k.document(document_id).GetPart(-1).RebuildModelEx(True), "rebuild model")
    return {"entity_id": entity_id, "measurements": k.measure(document_id)}


def state(k, document_id, entity_id, name=None, hidden=None, excluded=None):
    obj = k.entity(document_id, entity_id)
    for key, value in {"name": name, "hidden": hidden, "excluded": excluded}.items():
        if value is not None:
            setattr(obj, key, value)
    require(obj.Update(), "update entity state")
    require(k.document(document_id).GetPart(-1).RebuildModelEx(True), "rebuild model")
    return {
        "entity_id": entity_id,
        "name": obj.name,
        "hidden": obj.hidden,
        "excluded": obj.excluded,
    }


def delete(k, document_id, entity_id):
    obj = k.entity(document_id, entity_id)
    if obj.type in [k.constants[n] for n in ("o3d_edge", "o3d_face", "o3d_vertex")]:
        raise ValueError(
            "Deleting topology would delete its owning feature. Select the feature explicitly."
        )
    require(k.document(document_id).DeleteObject(obj), "delete feature")
    del k.entities[entity_id]
    return {"deleted": entity_id}


def edge_treatment(k, document_id, spec: EdgeTreatment):
    for token in spec.edges:
        edge = k.entity(document_id, token)
        if edge.type != k.constants["o3d_edge"] or not edge.GetDefinition().IsValid():
            raise ValueError(
                "All selections must be valid current edges; rediscover after rebuilding"
            )
    properties = {"tangent": spec.tangent}
    calls = [
        DefinitionCall(via=["array"], member="Add", arguments=[{"entity_id": token}])
        for token in spec.edges
    ]
    if spec.kind == "fillet":
        properties["radius"] = spec.size
    else:
        calls.insert(
            0,
            DefinitionCall(
                member="SetChamferParam", arguments=[True, spec.size, spec.second_size or spec.size]
            ),
        )
    return create(
        k,
        document_id,
        f"o3d_{spec.kind}",
        spec.name,
        FeatureSettings(properties=properties, calls=calls),
    )
