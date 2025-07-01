from hatchling.builders.hooks.plugin.interface import BuildHookInterface

class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "uv_workspaces"

    def initialize(*args) -> None:
        print("fuckry!")
