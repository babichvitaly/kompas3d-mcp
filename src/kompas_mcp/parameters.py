"""Native driving variable and physical material operations."""

import math

from .backend import require


def _collection(k, document_id, feature_id):
    part = k.document(document_id).GetPart(-1)
    if feature_id:
        collection = k.entity(document_id, feature_id).GetFeature().VariableCollection
    else:
        collection = part.GetFeature().VariableCollection
    # COM collections cache their contents, including user variables added in this session.
    require(collection.refresh(), "refresh native variables")
    return collection


def _info(k, variable):
    return {
        "name": variable.name,
        "value": variable.value,
        "expression": variable.Expression,
        "note": variable.note,
        "parameter_note": variable.parameterNote,
        "display_name": variable.displayName,
        "object": k.pack(variable),
    }


def list_variables(k, document_id, feature_id=None):
    collection = _collection(k, document_id, feature_id)
    return {"variables": [_info(k, collection.GetByIndex(i)) for i in range(collection.GetCount())]}


def set_variable(
    k, document_id, name, value=None, expression=None, feature_id=None, create=False, note=""
):
    if (value is None) == (expression is None):
        raise ValueError("Supply exactly one of value or expression")
    if not name.strip() or (expression is not None and not expression.strip()):
        raise ValueError("Variable name and expression cannot be blank")
    if value is not None and not math.isfinite(value):
        raise ValueError("Variable value must be finite")
    collection = _collection(k, document_id, feature_id)
    variable = collection.GetByName(name, True, False)
    if variable is None:
        if not create:
            raise ValueError("Variable not found; use create=true for a new user variable")
        if feature_id:
            raise ValueError(
                "Create user variables at part scope; feature variables are discovered"
            )
        variable = require(
            collection.AddNewVariable(name, value if value is not None else 0, note),
            "create variable",
        )
        variable.external = True
    if expression is not None:
        variable.Expression = expression
    else:
        # Setting value replaces the expression. Clearing Expression first can delete a user variable.
        variable.value = value
    # Part.RebuildModelEx rebuilds features but does not evaluate the document variable table.
    require(k.document(document_id).RebuildDocument(), "evaluate variables and rebuild document")
    collection = _collection(k, document_id, feature_id)
    variable = require(collection.GetByName(name, True, False), "read committed variable")
    result = _info(k, variable)
    result["measurements"] = k.measure(document_id)
    return result


def set_material(k, document_id, name, density_g_cm3):
    if not math.isfinite(density_g_cm3) or density_g_cm3 <= 0:
        raise ValueError("density_g_cm3 must be positive and finite")
    part = k.document(document_id).GetPart(-1)
    require(part.SetMaterial(name, density_g_cm3), "set part material")
    require(part.Update(), "update material")
    return {
        "material": part.material,
        "density_g_cm3": part.density,
        "measurements": k.measure(document_id),
    }
