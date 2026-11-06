"""Measured plane frames; no name-to-normal truth table or COM at import time."""

import math


def vector(value):
    if (len(value) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float))
                               or not math.isfinite(v) for v in value)):
        raise ValueError("Expected three finite coordinates")
    return [float(v) for v in value]


def plane_frame(points):
    if len(points) != 3:
        raise ValueError("Expected origin and two unit-axis points")
    p, pu, pv = [vector(q) for q in points]
    u, v = [[a-b for a, b in zip(q, p, strict=True)] for q in (pu, pv)]
    if (abs(sum(x*x for x in u)-1) > 1e-7 or abs(sum(x*x for x in v)-1) > 1e-7
            or abs(sum(a*b for a, b in zip(u, v, strict=True))) > 1e-7):
        raise ValueError("GetPoint3D frame is not orthonormal")
    normal = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
    return {"origin": p, "u": u, "v": v, "normal": normal}


def offset_for_displacement(points, displacement):
    """Signed native offset along measured normal; reject in-plane displacement.

    Caller measures the unoffset support frame, then verifies the final sketch
    frame before BeginEdit. This does not reinterpret legacy SketchSpec.offset.
    """
    normal = plane_frame(points)["normal"]
    delta = vector(displacement)
    signed = sum(a*b for a, b in zip(delta, normal, strict=True))
    if any(abs(a-signed*b) > 1e-7 for a, b in zip(delta, normal, strict=True)):
        raise ValueError("Displacement must be parallel to the measured normal")
    return {"offset": signed, "distance": abs(signed), "direction": signed > 0}


def sketch_preflight(k, entity, expected_points=None):
    from .documents import _cast

    native = _cast(k, k.app.TransferInterface(entity, k.constants["ksAPI7Dual"], 0), "ISketch")
    points = []
    for x, y in ((0., 0.), (1., 0.), (0., 1.)):
        result = native.GetPoint3D(x, y)
        if not isinstance(result, (tuple, list)) or len(result) != 4 or not result[0]:
            raise RuntimeError("GetPoint3D preflight failed; sketch edit blocked")
        points.append(vector(result[1:]))
    frame = plane_frame(points)
    if expected_points is not None:
        plane_frame(expected_points)
        if any(abs(a-b) > 1e-7 for p, q in zip(points, expected_points, strict=True)
               for a, b in zip(p, q, strict=True)):
            raise ValueError("Unexpected sketch world frame; sketch edit blocked")
    return {"points": points, **frame}
