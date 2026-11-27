"""Private-fixture adapter for the detached source helper, never installed by this runner."""

import importlib.util
import sys
from pathlib import Path

from native_owned_session import need, sha
from validate_specification_group_refresh import group_summary
from validate_specification_reference import occurrence
from validate_specification_text import TextAdapter


def load_frozen_helper(config):
    folder = Path(config['source_helper_package'])
    name = '_synthetic_source_refresh'
    need(name not in sys.modules and folder.is_dir(), 'Explicit fresh frozen helper package required')
    spec = importlib.util.spec_from_file_location(name, folder/'__init__.py',
                                                submodule_search_locations=[str(folder)])
    need(spec is not None and spec.loader is not None, 'Frozen source package unavailable')
    package = importlib.util.module_from_spec(spec)
    sys.modules[name] = package
    spec.loader.exec_module(package)
    module = importlib.import_module(name+'.specification_source')
    return module


class SourceAdapter(TextAdapter):
    def __init__(self, session, owner, bindings, sources):
        super().__init__(session, owner, bindings)
        self.sources, self.bindings = sources, bindings

    def source_evidence(self):
        self.session.guard()
        result = {p: {'sha256': sha(p), 'values': dict(values)} for p, values in self.sources.items()}
        self.session.guard()
        return result

    def group_summary(self):
        return group_summary(self.session, self.owner, self.bindings)

    def reset_source_property(self, uuid, pid):
        import pythoncom
        from win32com.client import VARIANT

        self.session.guard()
        path = self.bindings[uuid]
        need(len(path) == 1 and pid in {4, 5}, 'Only proven direct property4/5 source reset')
        keeper = self.session.cast(occurrence(self.session, self.owner, path), 'IPropertyKeeper')
        manager = self.session.cast(self.session.app, 'IPropertyMng')
        prop = manager.GetProperty(self.session.doc(self.owner), float(pid))
        need(prop is not None and float(prop.Id) == pid, 'Wrong source property identity')
        returned = keeper.SetPropertyValue(prop, VARIANT(pythoncom.VT_EMPTY, None), False)
        self.session.guard()
        return returned
