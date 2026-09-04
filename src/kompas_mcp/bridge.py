"""Discoverable API5/API7 access, interface casting and sequential checked batches."""

import inspect

from .advanced_models import ApiBatch


def resolve(k, value, results=None, document_id=None):
    if isinstance(value, dict):
        if set(value) == {"handle"}:
            return k.handles[value["handle"]]
        if set(value) == {"constant"}:
            return k.constants[value["constant"]]
        if set(value) == {"entity_id"}:
            if document_id is None:
                raise ValueError("entity_id references require a document-scoped feature operation")
            return k.entity(document_id, value["entity_id"])
        if set(value) == {"ref"}:
            if results is None or value["ref"] not in results:
                raise ValueError(f"Unknown batch reference {value['ref']}")
            result = results[value["ref"]]
            if isinstance(result, dict) and "handle" in result and "interface" in result:
                return k.handles[result["handle"]]
            return resolve(k, result, results, document_id)
        if set(value) == {"variant"}:
            import pythoncom
            from win32com.client import VARIANT

            spec = value["variant"]
            if not isinstance(spec, dict) or set(spec) != {"type", "values"}:
                raise ValueError("variant requires type and values")
            types = {
                "dispatch_array": pythoncom.VT_DISPATCH,
                "double_array": pythoncom.VT_R8,
                "int_array": pythoncom.VT_I4,
                "variant_array": pythoncom.VT_VARIANT,
            }
            if spec["type"] not in types or not isinstance(spec["values"], list):
                raise ValueError(
                    "Supported variants: dispatch_array, double_array, int_array, variant_array"
                )
            return VARIANT(
                pythoncom.VT_ARRAY | types[spec["type"]],
                resolve(k, spec["values"], results, document_id),
            )
        return {key: resolve(k, child, results, document_id) for key, child in value.items()}
    if isinstance(value, list):
        return [resolve(k, child, results, document_id) for child in value]
    return value


def describe_type(cls):
    methods = {}
    for base in reversed(cls.__mro__):
        for name, member in vars(base).items():
            if name.startswith("_") or not callable(member) or name in {"CLSID"}:
                continue
            # Only generated SDK members, not DispatchBaseClass infrastructure.
            if not base.__module__.startswith("win32com.gen_py"):
                continue
            try:
                signature = inspect.signature(member)
            except (TypeError, ValueError):
                continue
            params = []
            for p in signature.parameters.values():
                if p.name == "self":
                    continue
                default = p.default
                required = default is inspect.Parameter.empty or type(default).__name__ in {
                    "Empty",
                    "PyOleEmpty",
                }
                item = {"name": p.name, "required": required}
                if default is None or isinstance(default, (str, int, float, bool)):
                    item["default"] = default
                params.append(item)
            methods[name] = {"parameters": params, "help": member.__doc__}
    return {
        "interface": cls.__name__,
        "methods": methods,
        "readable": list(getattr(cls, "_prop_map_get_", {})),
        "writable": list(getattr(cls, "_prop_map_put_", {})),
    }


def catalog(k, query, library=None, offset=0, limit=40):
    if k.app is None:
        k.connect()
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("offset >= 0 and limit 1..100 required")
    libraries = [library] if library else ["kAPI5", "kAPI7"]
    if any(name not in {"kAPI5", "kAPI7"} for name in libraries):
        raise ValueError("library must be kAPI5 or kAPI7")
    matches = []
    for lib in libraries:
        for name, cls in vars(k.modules[lib]).items():
            if not inspect.isclass(cls) or not hasattr(cls, "_prop_map_get_"):
                continue
            if query.lower() in name.lower():
                matches.append(
                    {"library": lib, "interface": name, "iid": str(cls.CLSID), "help": cls.__doc__}
                )
    matches.sort(key=lambda item: (item["library"], item["interface"]))
    return {"total": len(matches), "offset": offset, "interfaces": matches[offset : offset + limit]}


def interface_type(k, library, interface):
    if k.app is None:
        k.connect()
    if library not in {"kAPI5", "kAPI7"}:
        raise ValueError("library must be kAPI5 or kAPI7")
    cls = getattr(k.modules[library], interface, None)
    if not inspect.isclass(cls) or not hasattr(cls, "_prop_map_get_"):
        raise ValueError("Interface not present in installed type library; use api_catalog")
    return cls


def cast(k, handle, library, interface):
    import pythoncom

    cls = interface_type(k, library, interface)
    obj = k.handles[handle]
    return k.pack(cls(obj._oleobj_.QueryInterface(cls.CLSID, pythoncom.IID_IDispatch)))


def invoke(k, obj, member, action, arguments, value):
    info = describe_type(type(obj))
    if action == "call" and member in info["methods"]:
        return getattr(obj, member)(*arguments)
    if action == "get" and member in info["readable"]:
        return getattr(obj, member)
    if action == "set" and member in info["writable"]:
        setattr(obj, member, value)
        return True
    raise ValueError(f"{type(obj).__name__}.{member} does not support {action}; describe it first")


def check_result(value, expect):
    if (expect == "truthy" and not value) or (expect == "not_null" and value is None):
        raise RuntimeError(f"SDK result {value!r} did not satisfy {expect}")


def batch(k, plan: ApiBatch):
    results = {}
    for step in plan.steps:
        try:
            obj = resolve(k, step.target, results)
            if not hasattr(obj, "_oleobj_"):
                raise ValueError("Step target must resolve to a COM handle")
            result = invoke(
                k,
                obj,
                step.member,
                step.action,
                resolve(k, step.arguments, results),
                resolve(k, step.value, results),
            )
            results[step.id] = k.pack(result)
            check_result(result, step.expect)
        except Exception as exc:  # noqa: BLE001 - preserve partial CAD results for every COM failure
            return {
                "completed": False,
                "failed_step": step.id,
                "results": results,
                "error": str(exc),
                "recovery": "Prior mutations remain. Inspect before retrying.",
            }
    return {"completed": True, "results": results}
