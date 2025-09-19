# dawnyawn/agent/thought_engine.py (Final Merged Prompt Version)
import re
import json
import logging
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
        # --- FINAL, HIGHLY CONSTRAINED SYSTEM PROMPT ---
        self.system_prompt_template = f"""
You are an expert penetration tester and command-line AI. Your SOLE function is to output a single, valid JSON object that represents the next best command to execute.

I. RESPONSE FORMATTING RULES (MANDATORY)
1.  **JSON ONLY:** Your entire response MUST be a single JSON object. Do not add explanations, markdown, conversational text, or anything else.
2.  **CORRECT SCHEMA:** The JSON object MUST have exactly two keys: `"tool_name"` and `"tool_input"`.
3.  **STRING INPUT:** The value for `"tool_input"` MUST be a single string. It ABSOLUTELY CANNOT be a list or an object.
4.  **VALID COMMAND SYNTAX:** The `"tool_input"` string must be a valid, executable shell command. Pay close attention to syntax. Use spaces to separate arguments, not commas.
    - **CORRECT EXAMPLE:** `ping -c 4 google.com`
    - **INCORRECT EXAMPLE:** `ping,google.com`

II. STRATEGIC ANALYSIS RULES (HOW TO THINK)
1.  **Analyze History:** Carefully review the entire execution history. Learn from previous command outputs, both successes and failures.
2.  **Learn from Failures:** If a command failed (e.g., with 'command not found' or an error message), you MUST NOT repeat the same mistake. Choose a different command or tool.
3.  **Be Efficient:** Do not run the same command twice if it has already succeeded. Use the information you have.
4.  **Goal Completion:** When you have gathered enough information to fully answer the user's goal, you MUST use the `finish_mission` tool. Provide a comprehensive summary in the `tool_input`.

III. AVAILABLE TOOLS:
{self.tool_manager.get_tool_manifest()}
"""

    def choose_next_action(self, goal: str, plan: List[TaskNode], history: List[Dict]) -> ToolSelection:
        logging.info("🤔 Thinking about the next step...")

        formatted_plan = "\n".join([f"  - {step.description}" for step in plan])
        formatted_history = "No actions taken yet."
        if history:
            formatted_history = ""
            for i, item in enumerate(history):
                command = item.get('command', 'N/A')
                obs_str = str(item.get('observation', ''))
                formatted_history += f"Action {i + 1}:\n  - Command: `{command}`\n  - Observation:\n```\n{obs_str}\n```\n"

        user_prompt = (
            f"Based on the goal, plan, and history below, what is the next command to execute? Remember your critical rules: respond with a single, valid JSON object and nothing else.\n\n"
            f"**Main Goal:** {goal}\n\n"
            f"**Strategic Plan:**\n{formatted_plan}\n\n"
            f"**Execution History:**\n{formatted_history}"
        )

        try:
            response = self.client.chat.completions.create(
                model=LLM_MODEL_NAME,
                messages=[
                    {"role": "system", "content": self.system_prompt_template},
                    {"role": "user", "content": user_prompt}
                ],
                timeout=LLM_REQUEST_TIMEOUT,
                response_format={"type": "json_object"}
            )
            raw_response = response.choices[0].message.content

            cleaned_response = _clean_json_response(raw_response)
            selection = ToolSelection.model_validate_json(cleaned_response)
            logging.info("AI's Next Action: %s", selection.tool_input)
            return selection

        except (ValidationError, json.JSONDecodeError) as e:
            logging.error("Critical Error during thought process: %s", type(e).__name__)
            try:
                logging.error("Model's malformed response: %s", raw_response)
            except NameError:
                logging.error("Model did not provide a response before the error occurred.")

            return ToolSelection(tool_name="finish_mission",
                                 tool_input="Mission failed: The AI produced an invalid JSON response and could not decide on a next action.")