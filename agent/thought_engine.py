# dawnyawn/agent/thought_engine.py (Final Version with Plan Status Updates)
import re
import json
import logging
from pydantic import BaseModel, TypeAdapter
from pydantic_core import ValidationError
from config import get_llm_client, LLM_MODEL_NAME, LLM_REQUEST_TIMEOUT
from tools.tool_manager import ToolManager
from models.task_node import TaskNode, TaskStatus
from typing import List, Dict


class ToolSelection(BaseModel):
    tool_name: str
    tool_input: str


def _clean_json_response(response_str: str) -> str:
    """Finds and extracts a JSON object/array from a string that might be wrapped in Markdown."""
    match = re.search(r'(\[.*\]|\{.*\})', response_str, re.DOTALL)
    if match:
        return match.group(0)
    return response_str


class ThoughtEngine:
    """AI Reasoning component. Decides the next action and updates the plan status."""

    def __init__(self, tool_manager: ToolManager):
        self.client = get_llm_client()
        self.tool_manager = tool_manager
        # --- FINAL, MOST ROBUST SYSTEM PROMPT ---
        self.system_prompt_template = f"""
You are an EXPERT PENETRATION TESTER and command-line AI.

I. RESPONSE FORMATTING RULES (MANDATORY)
1.  **JSON ONLY:** Your entire response MUST be a single JSON object. Do not add explanations or any other text.
2.  **CORRECT SCHEMA:** The JSON object MUST have exactly two keys: `"tool_name"` and `"tool_input"`.
3.  **STRING INPUT:** The value for `"tool_input"` MUST be a single string.

II. STRATEGIC ANALYSIS & COMMAND RULES (HOW TO THINK)
1.  **FOCUS ON PENDING TASKS:** Look at the strategic plan and focus only on tasks with a 'PENDING' status.
2.  **DO NOT REPEAT SUCCESS:** NEVER repeat a command that has already been successfully executed and has completed a task.
3.  **SELF-TERMINATING COMMANDS:** Commands MUST be self-terminating (e.g., use `ping -c 4`, not `ping`).
4.  **DO NOT INSTALL ANY TOOL:** 
5.  **Learn from Failures:** If a command fails, do not repeat it. Choose a different command.
6.  **Goal Completion:** Once all tasks in the plan are 'COMPLETED', you MUST use the `finish_mission` tool.

III. AVAILABLE TOOLS:
{self.tool_manager.get_tool_manifest()}
"""

    def _format_plan(self, plan: List[TaskNode]) -> str:
        """Formats the plan into a string for the AI, showing task status."""
        if not plan: return "No plan provided."
        return "\n".join([f"  - Task {task.task_id} [{task.status}]: {task.description}" for task in plan])

    def choose_next_action(self, goal: str, plan: List[TaskNode], history: List[Dict]) -> ToolSelection:
        logging.info("🤔 Thinking about the next step...")

        user_prompt = (
            f"Based on the goal, plan, and history below, decide the single best command to execute next to progress on a PENDING task. Respond with a single, valid JSON object.\n\n"
            f"**Main Goal:** {goal}\n\n"
            f"**Strategic Plan:**\n{self._format_plan(plan)}\n\n"
            f"**Execution History:**\n{json.dumps(history, indent=2)}"
        )
        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL_NAME,
                messages=[{"role": "system", "content": self.system_prompt_template},
                          {"role": "user", "content": user_prompt}],
                timeout=LLM_REQUEST_TIMEOUT,
                response_format={"type": "json_object"},
                temperature=0.2
            )
            raw_response = response.choices[0].message.content
            selection = ToolSelection.model_validate_json(_clean_json_response(raw_response))
            logging.info("AI's Next Action: %s", selection.tool_input)
            return selection
        except (ValidationError, json.JSONDecodeError) as e:
            logging.error("Critical Error during thought process: %s", type(e).__name__)
            return ToolSelection(tool_name="finish_mission",
                                 tool_input="Mission failed: The AI produced an invalid JSON response.")

    def update_plan_status(self, goal: str, plan: List[TaskNode], history: List[Dict]) -> List[TaskNode]:
        """Asks the AI to return the updated plan with new statuses."""
        plan_update_prompt = (
            "You are a project manager AI. Your job is to update a plan's status. "
            "Review the execution history and the strategic plan. Based on the output of the last command, "
            "identify which tasks in the plan are now complete. Your response MUST be ONLY the full plan, "
            f"returned as a JSON array, with the `status` field for any completed tasks changed to `{TaskStatus.COMPLETED}`. "
            "Do not add any other text.\n\n"
            f"**Execution History:**\n{json.dumps(history, indent=2)}\n\n"
            f"**Current Plan (in JSON array format):**\n{json.dumps([task.model_dump() for task in plan], indent=2)}"
        )
        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL_NAME,
                messages=[{"role": "system", "content": "You are a JSON-only plan updating assistant."},
                          {"role": "user", "content": plan_update_prompt}],
                timeout=LLM_REQUEST_TIMEOUT,
                response_format={"type": "json_object"},
                temperature=0.0
            )
            raw_response = response.choices[0].message.content
            # The AI might return the list inside a key, e.g. {"plan": [...]}, so we need to find the list.
            json_str = _clean_json_response(raw_response)
            json_data = json.loads(json_str)
            if isinstance(json_data, list):
                task_list_data = json_data
            elif isinstance(json_data, dict) and len(json_data.keys()) == 1:
                # Try to extract the list if it's the only value in a dict
                task_list_data = next(iter(json_data.values()))
            else:
                raise ValueError("JSON response is not a list or a single-key dictionary containing a list.")

            # Use Pydantic's TypeAdapter for validating a list of models
            list_of_tasks_adapter = TypeAdapter(List[TaskNode])
            return list_of_tasks_adapter.validate_python(task_list_data)
        except (ValidationError, json.JSONDecodeError, ValueError) as e:
            logging.error("AI failed to update plan status with valid JSON: %s", e)
            return None  # Return None to indicate failure