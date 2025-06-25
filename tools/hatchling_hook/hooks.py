from typing import Any
from hatchling.builders.hooks.plugin.interface import BuildHookInterface
from hatchling.plugin import hookimpl

@hookimpl
def hatch_register_build_hook():
    return UvWorkspaceBuildHook

class UvWorkspaceBuildHook(BuildHookInterface):
    PLUGIN_NAME = "uv-workspace"

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name != "wheel":
            return
        return
