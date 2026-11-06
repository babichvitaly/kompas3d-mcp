"""Typed API7 model identity checks, executed on the owning STA worker."""


def model_reference(k, feature, expected_reference=None):
    """Read Reference through IModelObject, never through IFeature7 Dispatch.

    A matching reference alone does not authorize mutation: the caller must also
    verify document identity/path and ownership. Delete stays on IFeature7.
    """
    from .documents import _cast

    reference = _cast(k, feature, "IModelObject").Reference
    if isinstance(reference, bool) or not isinstance(reference, int):
        raise TypeError("Expected an integer IModelObject.Reference")
    if expected_reference is not None:
        if isinstance(expected_reference, bool) or not isinstance(expected_reference, int):
            raise TypeError("Expected an integer reference precondition")
        if reference != expected_reference:
            raise ValueError("Model object reference changed; mutation blocked")
    return reference
