"""Method-specific Automation returns, not generic COM/HRESULT truthiness."""

from enum import Enum


class AutomationMethod(str, Enum):
    SAVE = 'IKompasDocument.Save'
    UPDATE_DRAWING_OBJECT = 'IDrawingObject.Update'
    CREATE_CONSTRAINT = 'IParametriticConstraint.Create'
    SET_BASE = 'IBranchs.SetBaseObject'


def normalize_automation_return(method: AutomationMethod, returned):
    """A normal return is only call evidence; it never proves persistence.

    Expects pywin32 Automation values. HRESULT wrappers need their own adapter;
    integer 0/-1/1 are deliberately not silently interpreted here. This contract
    does not generalize to unrelated Create/Update/SaveAs methods.
    """
    if not isinstance(method, AutomationMethod):
        raise TypeError('An explicit supported Automation method is required')
    if method is AutomationMethod.SAVE:
        if returned is not None:
            raise TypeError('Automation Save is void; expected None')
        return {'method': method.value, 'return_kind': 'void', 'returned': None,
                'call_completed': True, 'persistence_verified': False}
    if type(returned) is not bool:
        raise TypeError(f'{method.value} requires a boolean Automation result')
    return {'method': method.value, 'return_kind': 'boolean', 'returned': returned,
            'call_completed': returned, 'persistence_verified': False}
