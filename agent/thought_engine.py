# dawnyawn/agent/thought_engine.py (Final, Complete Version)
import re
import json  # <-- Import the json library
from pydantic import BaseModel
from pydantic_core import ValidationError
from config import get_llm_client, LLM_MODEL_NAME, LLM_REQUEST_TIMEOUT
from tools.tool_manager import ToolManager
from models.task_node import TaskNode
from typing import List, Dict


class ToolSelection(BaseModel):
    tool_name: str
    tool_input: str


def _clean_json_response(response_str: str) -> str:
    """Finds and extracts a JSON object from a string that might be wrapped in Markdown."""
    match = re.search(r'\{.*\}', response_str, re.DOTALL)
    if match:
        return match.group(0)
    return response_str


class ThoughtEngine:
    """AI Reasoning component. Decides the single next action based on a plan and history."""

    def __init__(self, tool_manager: ToolManager):
        self.client = get_llm_client()
        self.tool_manager = tool_manager
        # The system prompt is now generated dynamically in choose_next_action
        self.system_prompt_template = f"""
You are an expert penetration tester AI. Your job is to select the next command to execute to achieve the user's goal.

**CRUCIAL ANALYSIS INSTRUCTIONS:**
1.  **Analyze the Entire History:** Carefully review all previous actions and their observations.
2.  **Learn from Failures:** If a previous step has a status of `FAILURE`, you MUST analyze the `full_output` to understand why. Do not repeat failed commands. If a tool is "not found", do not try to use it again.
3.  **Extract Valuable Data:** Even in a `FAILURE` observation (e.g., due to a timeout), the `full_output` may contain critical information like open ports or vulnerabilities. Use this partial data to inform your next step.
4.  **Be Efficient:** Do not run the same scan twice. Use the information you already have.
5.  **Use Real Commands:** Only generate valid, real-world shell commands. Do not invent `nmap` scripts or options.
6.  **Goal Completion:** When you have gathered enough information to produce the final report described in the goal, you MUST use the `finish_mission` tool.

**Your Response:**
Your response MUST be a JSON object with EXACTLY TWO keys: "tool_name" and "tool_input".

**Available Tools:**
{self.tool_manager.get_tool_manifest()}
"""

    def choose_next_action(self, goal: str, plan: List[TaskNode], history: List[Dict]) -> ToolSelection:
        print(f"\n🤔 Thinking about the next step...")

        # Format the plan and history for the prompt
        formatted_plan = "\n".join([f"  - {step.description}" for step in plan])

        formatted_history = "No actions taken yet."
        if history:
            # We now use json.dumps to format the observation cleanly and robustly
            formatted_history = ""
            for i, item in enumerate(history):
                # Use .get() for safety in case a key is missing
                command = item.get('command', 'N/A')
                observation = item.get('observation', {})
                # Pretty-print the observation JSON for the LLM
                obs_str = json.dumps(observation, indent=2)
                formatted_history += f"Action {i + 1}:\n  - Command: `{command}`\n  - Observation:\n{obs_str}\n"

        user_prompt = (
            f"Main Goal: {goal}\n\n"
            f"Strategic Plan:\n{formatted_plan}\n\n"
            f"Execution History:\n{formatted_history}\n\n"
            "Based on all the information above, what is your single best command for your next action? Respond with a JSON object."
        )

        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL_NAME,
                messages=[
                    {"role": "system", "content": self.system_prompt_template},
                    {"role": "user", "content": user_prompt}
                ],
                timeout=LLM_REQUEST_TIMEOUT
            )
            raw_response = response.choices[0].message.content
            cleaned_response = _clean_json_response(raw_response)

            selection = ToolSelection.model_validate_json(cleaned_response)
            print(f"  > AI's Next Action: {selection.tool_input}")
            return selection

        except (ValidationError) as e:
            print(f"\n❌ Critical Error during thought process: {type(e).__name__}")
            # Check if raw_response is available to show what the model sent
            try:
                print(f"   Model's raw response: \"{raw_response}\"")
            except NameError:
                print("   Model did not provide a response before the error occurred.")

            # Return a special action that signals failure, allowing the loop to terminate gracefully
            return ToolSelection(tool_name="finish_mission",
                                 tool_input="Mission failed: The AI could not decide on a valid next action.")