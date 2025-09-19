# dawnyawn/agent/task_manager.py (Corrected for Circular Import)
import os
import json
import logging
from openai import APITimeoutError
from models.task_node import TaskNode
# Keep this import at the top as it's unlikely to cause a cycle
from reporting.report_generator import create_report

# --- Constants ---
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECTS_DIR = os.path.join(PROJECT_ROOT, "Projects")
SESSION_FILE = os.path.join(PROJECTS_DIR, "mission_session.json")


class TaskManager:
    """Orchestrates the agent's lifecycle using a stateless, file-based execution model."""

    def __init__(self, goal: str):
        # --- DELAYED IMPORTS to prevent circular dependency ---
        from agent.agent_scheduler import AgentScheduler
        from agent.thought_engine import ThoughtEngine
        from tools.tool_manager import ToolManager
        from services.mcp_client import McpClient

        self.goal = goal
        self.plan: list[TaskNode] = []
        self.mission_history = []

        # Now, initialize the components
        self.scheduler = AgentScheduler()
        self.thought_engine = ThoughtEngine(ToolManager())
        self.mcp_client = McpClient()

        # Ensure the Projects directory exists for outputs and sessions
        os.makedirs(PROJECTS_DIR, exist_ok=True)

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
                logging.warning("Session file goal '%s' does not match current goal '%s'. Starting fresh.",
                                state.get("goal"), self.goal)
                return False

            self.plan = [TaskNode(**task_data) for task_data in state.get("plan", [])]
            self.mission_history = state.get("mission_history", [])
            logging.info("Successfully loaded and resumed mission from session file.")
            return True
        except (json.JSONDecodeError, TypeError) as e:
            logging.error("Failed to load session file due to corruption: %s. Starting fresh.", e)
            return False

    def run(self):
        """Executes the main Plan -> Execute loop for the agent's mission."""
        if not self._load_state():
            # --- PLANNING PHASE (for new missions) ---
            logging.info("Starting new mission for goal: %s", self.goal)
            try:
                self.plan = self.scheduler.create_plan(self.goal)
                if not self.plan:
                    logging.error("Mission aborted: Agent failed to generate a valid plan.")
                    return

                logging.info("High-Level Plan Created:")
                for task in self.plan:
                    logging.info("  - %s", task.description)

                if input("\nProceed with this plan? (y/n): ").lower() != 'y':
                    logging.info("Mission aborted by user.")
                    return

                self._save_state()

            except (APITimeoutError, KeyboardInterrupt) as e:
                logging.error("Mission aborted during planning phase: %s", e)
                return

        # --- EXECUTION LOOP (for new or resumed missions) ---
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