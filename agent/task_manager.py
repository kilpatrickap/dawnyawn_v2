# dawnyawn/agent/task_manager.py (Simplified Version)
import json
from openai import APITimeoutError
from models.task_node import TaskNode
from agent.agent_scheduler import AgentScheduler
from agent.thought_engine import ThoughtEngine
from tools.tool_manager import ToolManager
from services.event_manager import EventManager
from services.mcp_client import McpClient


class TaskManager:
    """Orchestrates the Plan -> Approve -> Execute loop with JSON observations."""

    def __init__(self, goal: str):
        self.goal = goal
        self.mission_history = []
        self.scheduler = AgentScheduler()
        self.thought_engine = ThoughtEngine(ToolManager())
        self.event_manager = EventManager()
        self.mcp_client = McpClient()

    def run(self):
        self.event_manager.log_event("INFO", f"Starting mission for goal: {self.goal}")
        try:
            plan = self.scheduler.create_plan(self.goal)
            if not plan: print("Mission aborted: No valid plan."); return
            print("\n📝 High-Level Plan Created:");
            [print(f"  - {task.description}") for task in plan]
            if input("\nProceed? (y/n): ").lower() != 'y': print("Mission aborted."); return
        except (APITimeoutError, KeyboardInterrupt) as e:
            print(f"\nMission aborted during planning: {e}");
            return

        session_id = self.mcp_client.start_session()
        try:
            while True:
                action = self.thought_engine.choose_next_action(self.goal, plan, self.mission_history)
                if action.tool_name == "finish_mission":
                    self.event_manager.log_event("SUCCESS", "AI decided mission is complete.")
                    self.mission_history.append(
                        {"command": "finish_mission", "observation": {"key_finding": action.tool_input}})
                    break

                # The server now returns a perfect JSON observation (as a dict)
                observation = self.mcp_client.execute_command(session_id, action.tool_input)
                self.mission_history.append({"command": action.tool_input, "observation": observation})

                if len(self.mission_history) >= 10:
                    self.event_manager.log_event("WARN", "Max step limit reached.");
                    break
        except (APITimeoutError, KeyboardInterrupt) as e:
            print(f"\nMission aborted during execution: {e}")
        finally:
            self.mcp_client.end_session(session_id)
            self._generate_final_report()

    def _generate_final_report(self):
        print("\n\n--- DAWNYAWN MISSION REPORT ---")
        print(f"Goal: {self.goal}\n")
        for i, item in enumerate(self.mission_history):
            print(f"Step {i + 1}:")
            print(f"  - Action: `{item['command']}`")
            # Pretty-print the JSON observation for the report
            observation_str = json.dumps(item.get('observation', {}), indent=2)
            print(f"  - Observation:\n{observation_str}\n")