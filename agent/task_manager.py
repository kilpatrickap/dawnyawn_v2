# dawnyawn/agent/task_manager.py (Final Version with Plan Status Updates)
import os
import json
import logging
from openai import APITimeoutError
from models.task_node import TaskNode, TaskStatus
from reporting.report_generator import create_report

# --- Constants ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_DIR = os.path.join(PROJECT_ROOT, "Projects")
SESSION_FILE = os.path.join(PROJECTS_DIR, "mission_session.json")


class TaskManager:
    """Orchestrates the agent's lifecycle with dynamic plan status updates."""

    def __init__(self, goal: str):
        from agent.agent_scheduler import AgentScheduler
        from agent.thought_engine import ThoughtEngine
        from tools.tool_manager import ToolManager
        from services.mcp_client import McpClient

        self.goal = goal
        self.plan: list[TaskNode] = []
        self.mission_history = []
        self.scheduler = AgentScheduler()
        self.thought_engine = ThoughtEngine(ToolManager())
        self.mcp_client = McpClient()
        os.makedirs(PROJECTS_DIR, exist_ok=True)

    def initialize_mission(self):
        """Asks user whether to resume an old mission or start a new one."""
        if os.path.exists(SESSION_FILE):
            resume = input("\nAn existing session file was found. Do you want to resume? (y/n): ").lower()
            if resume != 'y':
                os.remove(SESSION_FILE)
                logging.info("Previous session file deleted. Starting a fresh mission.")

    def _update_plan_status(self):
        """Asks the ThoughtEngine to review history and mark tasks in the plan as COMPLETED."""
        logging.info("📝 Updating plan status based on recent actions...")
        # This is a special call to the thought engine to get its assessment
        updated_plan = self.thought_engine.update_plan_status(self.goal, self.plan, self.mission_history)
        if updated_plan:
            self.plan = updated_plan
            for task in self.plan:
                if task.status == TaskStatus.COMPLETED:
                    logging.info("  - Status Updated: Task %d is COMPLETED.", task.task_id)

    # ... ( _save_state and _load_state are unchanged) ...
    def _save_state(self):
        """Saves the current mission goal, plan, and history to a session file."""
        state = {
            "goal": self.goal,
            "plan": [task.model_dump() for task in self.plan],
            "mission_history": self.mission_history
        }
        with open(SESSION_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=4)
        logging.info("Mission state saved to session file.")

    def _load_state(self):
        """Loads mission state from the session file if it exists and matches the goal."""
        if not os.path.exists(SESSION_FILE):
            logging.info("No existing session file found. Starting a new mission.")
            return False
        try:
            with open(SESSION_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)
            if state.get("goal") != self.goal:
                logging.warning("Session file goal does not match. Starting fresh.")
                os.remove(SESSION_FILE)
                return False
            self.plan = [TaskNode(**task_data) for task_data in state.get("plan", [])]
            self.mission_history = state.get("mission_history", [])
            logging.info("Successfully loaded and resumed mission from session file.")
            return True
        except (json.JSONDecodeError, TypeError) as e:
            logging.error("Failed to load session file due to corruption. Starting fresh.", e)
            return False

    def run(self):
        """Executes the main Plan -> Execute loop for the agent's mission."""
        if not self._load_state():
            # PLANNING PHASE
            logging.info("Starting new mission for goal: %s", self.goal)
            try:
                self.plan = self.scheduler.create_plan(self.goal)
                if not self.plan:
                    logging.error("Mission aborted: Agent failed to generate a valid plan.")
                    return
                logging.info("High-Level Plan Created:")
                for task in self.plan:
                    logging.info("  %d. %s", task.task_id, task.description)
                if input("\nProceed with this plan? (y/n): ").lower() != 'y':
                    logging.info("Mission aborted by user.")
                    return
                self._save_state()
            except (APITimeoutError, KeyboardInterrupt) as e:
                logging.error("Mission aborted during planning phase: %s", e)
                return

        # EXECUTION LOOP
        try:
            while True:
                action = self.thought_engine.choose_next_action(self.goal, self.plan, self.mission_history)

                if action.tool_name == "finish_mission":
                    logging.info("AI has decided the mission is complete.")
                    self.mission_history.append({"command": "finish_mission", "observation": action.tool_input})
                    break

                filename, file_content = self.mcp_client.execute_command(action.tool_input)

                if filename and file_content is not None:
                    local_filepath = os.path.join(PROJECTS_DIR, filename)
                    with open(local_filepath, 'w', encoding='utf-8') as f:
                        f.write(file_content)
                    logging.info("Observation saved to '%s'", local_filepath)
                    observation = file_content
                else:
                    observation = file_content
                    logging.error("Command execution failed: %s", observation)

                self.mission_history.append({"command": action.tool_input, "observation": observation})

                # --- THE FIX: After an action, update the plan status ---
                self._update_plan_status()
                self._save_state()

                if len(self.mission_history) >= 20:
                    logging.warning("Max step limit (20) reached. Terminating mission.")
                    break
        except (APITimeoutError, KeyboardInterrupt) as e:
            logging.error("Mission aborted during execution loop: %s", e)
        finally:
            self._generate_final_report()
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
                logging.info("Session file cleaned up.")

    def _generate_final_report(self):
        """Generates the final mission report using the dedicated reporting module."""
        logging.info("Generating final mission report...")
        if not self.mission_history:
            logging.warning("No actions were taken, cannot generate a report.")
            return
        create_report(self.goal, self.mission_history)