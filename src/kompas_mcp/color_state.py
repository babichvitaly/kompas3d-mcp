"""Read IColorParam7 state without treating root UseColor as occurrence state."""


def color_state(color_param, scope, expected_color=None):
    """Report raw native state; does not infer rendered appearance/inheritance.

    root UseColor may be undefined (-1/None); occurrence 0 is an explicit native
    value, not a missing value. A matching Color alone is not visual acceptance.
    """
    if scope not in {"root", "occurrence"}:
        raise ValueError("Specify root or occurrence scope")
    color = color_param.Color
    if isinstance(color, bool) or not isinstance(color, int) or not 0 <= color <= 0xFFFFFF:
        raise ValueError("Expected a valid RGB COLORREF")
    raw = color_param.UseColor
    defined = raw in (0, 1) and raw is not None
    return {"scope": scope, "color": color, "use_color_raw": raw,
            "use_color_state": ("defined" if defined else
                                "root_undefined" if scope == "root" else "unknown"),
            "color_matches": None if expected_color is None else color == expected_color,
            "appearance_verified": False}
