# dawnyawn/tools/tool_manager.py (Interactive Version)
from tools.base_tool import BaseTool
from tools.os_command_tool import OsCommandTool


class ToolManager:
    """Function Registry that holds and provides access to all available tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._register_tool(OsCommandTool())  # This tool is now conceptual

    def _register_tool(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get_tool_manifest(self) -> str:
        """
        Returns a formatted string of all available tools, including special commands.
        """
        manifest = "Your response must select one of the following available tools:\n"
        # Add the special 'finish' command to the manifest for the LLM
        manifest += "- Tool Name: `finish_mission`\n  Description: Use this tool when you have fully accomplished the user's goal and have all the information you need. Provide a final summary of your findings as the input.\n"

        for tool in self._tools.values():
            manifest += f"- Tool Name: `{tool.name}`\n  Description: {tool.description}\n"
        return manifest