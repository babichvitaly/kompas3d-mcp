"""Validated geometry in millimetres and degrees, independent of COM."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Number = Annotated[float, Field(allow_inf_nan=False)]
Positive = Annotated[Number, Field(gt=0)]
Point = tuple[Number, Number]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Circle(Model):
    kind: Literal["circle"] = "circle"
    center: Point = (0, 0)
    radius: Positive


class Polyline(Model):
    kind: Literal["polyline"] = "polyline"
    points: Annotated[list[Point], Field(min_length=2, max_length=2000)]
    closed: bool = True
    construction: bool = False

    @model_validator(mode="after")
    def nondegenerate(self):
        if self.closed and len(self.points) < 3:
            raise ValueError("Closed polylines need at least three vertices")
        pairs = list(zip(self.points, self.points[1:]))
        if self.closed:
            pairs.append((self.points[-1], self.points[0]))
        if any(a == b for a, b in pairs):
            raise ValueError("Duplicate adjacent vertices; do not repeat the closing vertex")
        return self


class Arc(Model):
    kind: Literal["arc"] = "arc"
    center: Point
    radius: Positive
    start_angle: Number
    end_angle: Number
    counterclockwise: bool = True


Curve = Annotated[Circle | Polyline | Arc, Field(discriminator="kind")]


class SketchSpec(Model):
    name: str = "Sketch"
    plane: Literal["XY", "XZ", "YZ"] = "XY"
    offset: Number = 0
    support_entity_id: str | None = None
    curves: Annotated[list[Curve], Field(min_length=1, max_length=2000)]

    @model_validator(mode="after")
    def one_support(self):
        if self.support_entity_id and (self.offset != 0 or self.plane != "XY"):
            raise ValueError("When support_entity_id is set, omit plane and offset")
        return self


class ExtrusionSpec(Model):
    sketch_id: str
    name: str = "Extrusion"
    operation: Literal["add", "cut"] = "add"
    depth: Positive
    reverse: bool = False
    draft_angle: Annotated[Number, Field(ge=0, lt=90)] = 0


class RevolutionSpec(Model):
    sketch_id: str
    name: str = "Revolution"
    operation: Literal["add", "cut"] = "add"
    angle: Annotated[Number, Field(gt=0, le=360)] = 360
    reverse: bool = False
