# dawnyawn/services/mcp_client.py (Simplified Version)
import requests
from typing import Dict
from config import service_config

class McpClient:
    """Handles session-based communication with the smart execution server."""

    def start_session(self) -> str:
        try:
            response = requests.post(f"{service_config.KALI_DRIVER_URL}/session/start", timeout=60)
            response.raise_for_status()
            return response.json()["session_id"]
        except requests.exceptions.RequestException as e:
            raise RuntimeError(f"FATAL: Could not start a session. Is the server running? Details: {e}")

    def execute_command(self, session_id: str, command: str) -> Dict:
        """Executes a command and expects a structured JSON observation in return."""
        try:
            response = requests.post(
                f"{service_config.KALI_DRIVER_URL}/session/execute",
                json={"session_id": session_id, "command": command},
                timeout=1800
            )
            response.raise_for_status()
            return response.json() # Returns the full JSON observation as a dict
        except requests.exceptions.RequestException as e:
            return {"status": "FAILURE", "key_finding": f"Agent-side connection error: {e}", "full_output": ""}

    def end_session(self, session_id: str):
        try:
            requests.post(f"{service_config.KALI_DRIVER_URL}/session/end", json={"session_id": session_id}, timeout=60)
            print("✅ Session terminated successfully on the server.")
        except requests.exceptions.RequestException as e:
            print(f"⚠️  Warning: Failed to terminate session. {e}")