"""Small API5 adapter. Dynamic COM dispatch is confined to this module."""

import os
from pathlib import Path
from uuid import uuid4

from .models import Arc, Circle, ExtrusionSpec, RevolutionSpec, SketchSpec


def require(value, action):
    if not value:
        raise RuntimeError(f"KOMPAS rejected {action}. Inspect the document before retrying.")
    return value


def output_path(path: str, extensions: set[str], overwrite: bool = False) -> Path:
    target = Path(path).expanduser()
    if not target.is_absolute():
        raise ValueError("Use an absolute output path")
    target = target.resolve()
    if target.suffix.lower() not in extensions:
        raise ValueError(f"Expected one of {sorted(extensions)}")
    if target.exists() and not overwrite:
        raise FileExistsError(f"Output already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


class Kompas:
    def __init__(self):
        self.app = None
        self.api = None
        self.constants = {}
        self.documents = {}
        self.entities = {}
        self.handles = {}

    def connect(self, visible=True):
        import pythoncom
        from win32com import client

        if self.app is None:
            root = os.getenv("KOMPAS_SDK_PATH")
            candidates = (
                [Path(root)]
                if root
                else sorted(Path("C:/Program Files/ASCON").glob("KOMPAS*/SDK"), reverse=True)
            )
            sdk = next((p for p in candidates if (p / "lib/kAPI5.tlb").exists()), None)
            if sdk is None:
                raise RuntimeError(
                    "SDK not found. Set KOMPAS_SDK_PATH to the installed SDK folder."
                )
            modules = {}
            for name in ("kAPI5", "kAPI7", "ksConstants", "ksConstants3D"):
                typelib = pythoncom.LoadTypeLib(str(sdk / "lib" / f"{name}.tlb"))
                guid, lcid, _, major, minor, *_ = typelib.GetLibAttr()
                modules[name] = client.gencache.EnsureModule(guid, lcid, major, minor)
            api = modules["kAPI5"]
            raw = client.Dispatch("KOMPAS.Application.5")
            self.app = api.KompasObject(
                raw._oleobj_.QueryInterface(api.KompasObject.CLSID, pythoncom.IID_IDispatch)
            )
            self.api = api
            self.sdk = sdk
            self.modules = modules
            for name in ("ksConstants", "ksConstants3D"):
                self.constants.update(
                    {
                        k: v
                        for k, v in vars(modules[name].constants).items()
                        if not k.startswith("_")
                    }
                )
        self.app.Visible = visible
        return {
            "connected": True,
            "version": list(self.app.ksGetSystemVersion()),
            "application": self.pack(self.app),
            "application7": self.pack(self.app.ksGetApplication7()),
        }

    def attach_active(self):
        self.connect()
        doc = self.app.ActiveDocument3D()
        if doc is None:
            raise ValueError("No active 3D document")
        token = uuid4().hex
        self.documents[token] = doc
        return {"document_id": token, "path": doc.fileName, "name": doc.GetPart(-1).name}

    def measure(self, document_id):
        part = self.document(document_id).GetPart(-1)
        # SDK Include/ldefin2d.h: ST_MIX_MM=0x1, ST_MIX_KG=0x10 (not in the TLB).
        props = require(part.CalcMassInertiaProperties(0x1 | 0x10), "measure part")
        return {
            "volume_mm3": props.v,
            "area_mm2": props.F,
            "mass_kg": props.m,
            "center_mm": [props.xc, props.yc, props.zc],
            "body_count": part.BodyCollection().GetCount(),
        }

    def document(self, document_id):
        if document_id not in self.documents:
            raise ValueError("Unknown document_id. Connect and create/open a document first.")
        return self.documents[document_id]

    def new_document(self, name):
        self.connect()
        doc = self.api.ksDocument3D(self.app.Document3D())
        require(doc.Create(False, True), "create part")
        doc.GetPart(-1).name = name
        token = uuid4().hex
        self.documents[token] = doc
        return {"document_id": token, "name": name}

    def open_document(self, path):
        source = Path(path).resolve()
        if not source.is_file() or source.suffix.lower() not in {
            ".m3d",
            ".a3d",
            ".stp",
            ".step",
            ".igs",
            ".iges",
            ".stl",
        }:
            raise ValueError("Expected an existing native model or STEP/IGES/STL file")
        self.connect()
        doc = self.api.ksDocument3D(self.app.Document3D())
        require(doc.Open(str(source), False), "open document")
        token = uuid4().hex
        self.documents[token] = doc
        return {"document_id": token, "path": str(source)}

    def entity(self, document_id, entity_id):
        entry = self.entities.get(entity_id)
        if entry is None or entry[0] != document_id:
            raise ValueError("Entity does not belong to this document or is stale")
        return entry[1]

    def remember(self, document_id, entity):
        token = uuid4().hex
        self.entities[token] = (document_id, entity)
        return token

    def sketch(self, document_id: str, spec: SketchSpec):
        part = self.document(document_id).GetPart(-1)
        plane = part.GetDefaultEntity(
            self.constants[
                {"XY": "o3d_planeXOY", "XZ": "o3d_planeXOZ", "YZ": "o3d_planeYOZ"}[spec.plane]
            ]
        )
        if spec.support_entity_id:
            plane = self.entity(document_id, spec.support_entity_id)
        if spec.offset:
            plane_offset = part.NewEntity(self.constants["o3d_planeOffset"])
            definition = plane_offset.GetDefinition()
            require(definition.SetPlane(plane), "set offset reference plane")
            definition.offset = abs(spec.offset)
            definition.direction = spec.offset > 0
            require(plane_offset.Create(), "create offset plane")
            plane = plane_offset
        entity = part.NewEntity(self.constants["o3d_sketch"])
        entity.name = spec.name
        definition = entity.GetDefinition()
        require(definition.SetPlane(plane), "set sketch plane")
        require(entity.Create(), "create sketch")
        drawing = require(definition.BeginEdit(), "begin sketch edit")
        try:
            for curve in spec.curves:
                if isinstance(curve, Circle):
                    require(drawing.ksCircle(*curve.center, curve.radius, 1), "draw circle")
                elif isinstance(curve, Arc):
                    require(
                        drawing.ksArcByAngle(
                            *curve.center,
                            curve.radius,
                            curve.start_angle,
                            curve.end_angle,
                            1 if curve.counterclockwise else -1,
                            1,
                        ),
                        "draw arc",
                    )
                else:
                    pairs = list(zip(curve.points, curve.points[1:]))
                    if curve.closed:
                        pairs.append((curve.points[-1], curve.points[0]))
                    for a, b in pairs:
                        require(
                            drawing.ksLineSeg(*a, *b, 3 if curve.construction else 1), "draw line"
                        )
        finally:
            require(definition.EndEdit(), "end sketch edit")
        return {"sketch_id": self.remember(document_id, entity), "name": spec.name}

    def feature(self, document_id: str, spec: ExtrusionSpec | RevolutionSpec):
        sketch = self.entity(document_id, spec.sketch_id)
        part = self.document(document_id).GetPart(-1)
        before = self.measure(document_id)["volume_mm3"]
        family = "Extrusion" if isinstance(spec, ExtrusionSpec) else "Rotated"
        kind = "boss" if spec.operation == "add" else "cut"
        entity = part.NewEntity(self.constants[f"o3d_{kind}{family}"])
        entity.name = spec.name
        definition = entity.GetDefinition()
        require(definition.SetSketch(sketch), "set feature sketch")
        # API5 cuts invert the sketch normal. Public extrusions share a geometric direction.
        api_reverse = spec.reverse ^ (isinstance(spec, ExtrusionSpec) and spec.operation == "cut")
        definition.directionType = self.constants["dtReverse" if api_reverse else "dtNormal"]
        if isinstance(spec, ExtrusionSpec):
            require(
                definition.SetSideParam(
                    not api_reverse, self.constants["etBlind"], spec.depth, spec.draft_angle, False
                ),
                "set extrusion depth",
            )
        else:
            definition.toroidShapeType = False
            require(definition.SetSideParam(not spec.reverse, spec.angle), "set revolution angle")
        require(entity.Create(), f"create {kind} {family}")
        feature_id = self.remember(document_id, entity)
        after = self.measure(document_id)["volume_mm3"]
        if (spec.operation == "cut" and after >= before - 1e-7) or (
            spec.operation == "add" and after <= before + 1e-7
        ):
            raise RuntimeError(
                f"Feature {feature_id} was created but did not change volume as "
                "expected. It remains in the document; inspect direction/intersection."
            )
        return {"feature_id": feature_id, "name": spec.name, "volume_mm3": after}

    def inspect_document(self, document_id):
        doc = self.document(document_id)
        part = doc.GetPart(-1)
        bounds = part.GetGabarit(True, True)
        return {
            "document_id": document_id,
            "name": part.name,
            "bounds_raw": list(bounds),
            "bounds_units": "mm",
            "measurements": self.measure(document_id),
            "document": self.pack(doc),
            "part": self.pack(part),
            "session_entities": [
                {"entity_id": k, "name": e.name, "object": self.pack(e)}
                for k, (d, e) in self.entities.items()
                if d == document_id
            ],
        }

    def save(self, document_id, path, overwrite=False):
        doc = self.document(document_id)
        target = output_path(path, {".m3d", ".a3d"}, overwrite)
        require(doc.SaveAs(str(target)), "save native document")
        return self.file_result(target)

    def export(self, document_id, path, overwrite=False):
        target = output_path(path, {".step", ".stp", ".stl", ".igs", ".iges"}, overwrite)
        params = self.document(document_id).AdditionFormatParam()
        require(params.Init(), "initialize export parameters")
        format_name = {
            ".step": "format_STEP",
            ".stp": "format_STEP",
            ".stl": "format_STL",
            ".igs": "format_IGES",
            ".iges": "format_IGES",
        }[target.suffix.lower()]
        params.format = self.constants[format_name]
        require(
            self.document(document_id).SaveAsToAdditionFormat(str(target), params), "export model"
        )
        return self.file_result(target)

    def preview(self, document_id, path):
        target = output_path(path, {".png"})
        params = self.document(document_id).RasterFormatParam()
        require(params.Init(), "initialize raster parameters")
        params.format = self.constants["ksRasterFormatPNG"]
        params.colorBPP = 24
        params.extResolution = 96
        require(
            self.document(document_id).SaveAsToRasterFormat(str(target), params), "render preview"
        )
        return self.file_result(target)

    @staticmethod
    def file_result(target):
        if not target.is_file() or not target.stat().st_size:
            raise RuntimeError(f"KOMPAS returned success but output is missing or empty: {target}")
        return {"path": str(target), "bytes": target.stat().st_size}

    def pack(self, value):
        if hasattr(value, "_oleobj_"):
            token = uuid4().hex
            self.handles[token] = value
            return {"handle": token, "interface": type(value).__name__}
        if isinstance(value, (tuple, list)):
            return [self.pack(v) for v in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    def describe(self, handle):
        from .bridge import describe_type

        return describe_type(type(self.handles[handle]))

    def api_call(self, handle, member, action, arguments, value):
        from .bridge import invoke, resolve

        return self.pack(
            invoke(
                self,
                self.handles[handle],
                member,
                action,
                resolve(self, arguments),
                resolve(self, value),
            )
        )
