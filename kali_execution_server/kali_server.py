# kali_execution_server/kali_server.py (Smart Service Version)
import uvicorn
import traceback
import uuid
import os
import re
import json
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ValidationError
from typing import Dict
from dotenv import load_dotenv

# --- LLM Integration ---
from openai import OpenAI, APITimeoutError

# Load server-specific environment variables
load_dotenv()

# --- Local Imports ---
from kali_driver.driver import KaliManager, KaliContainer


# --- Pydantic Model for Structured Output ---
class Observation(BaseModel):
    status: str
    key_finding: str
    full_output: str


# --- LLM Client Setup ---
LLM_MODEL_NAME = os.getenv("LLM_MODEL")
LLM_REQUEST_TIMEOUT = 120.0
MAX_SUMMARY_INPUT_LENGTH = 2000
formatter_client = OpenAI(
    base_url=os.getenv("OLLAMA_BASE_URL"),
    api_key=os.getenv("OLLAMA_API_KEY"),
)

app = FastAPI(title="DawnYawn Smart Execution Server")
print("Initializing Kali Docker Manager...")
kali_manager = KaliManager()
active_sessions: Dict[str, KaliContainer] = {}
print("Kali Docker Manager initialized.")


# --- Helper Functions ---
def _clean_json_response(response_str: str) -> str:
    match = re.search(r'\{.*\}', response_str, re.DOTALL)
    if match: return match.group(0)
    return response_str


def _format_output_as_json(command: str, raw_output: str) -> dict:
    """Uses an LLM to format raw text into a structured JSON Observation."""
    print("   ✍️  Server is formatting output into structured JSON...")
    if len(raw_output) > MAX_SUMMARY_INPUT_LENGTH:
        truncated_output = raw_output[:MAX_SUMMARY_INPUT_LENGTH]
    else:
        truncated_output = raw_output

    json_schema = Observation.model_json_schema()
    prompt = (
        f"You are a data formatting expert. Convert the raw output from the command `{command}` into a structured JSON object. "
        f"The `key_finding` should be a very brief, one-sentence summary.\n\n"
        f"RAW OUTPUT:\n---\n{truncated_output}\n---\n\n"
        f"Your response MUST BE ONLY the single, valid JSON object conforming to this schema:\n{json.dumps(json_schema, indent=2)}"
    )
    try:
        response = formatter_client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[{"role": "system", "content": "You are a JSON formatting assistant."},
                      {"role": "user", "content": prompt}],
            timeout=LLM_REQUEST_TIMEOUT
        )
        json_string = _clean_json_response(response.choices[0].message.content)
        # Validate the JSON before returning
        return Observation.model_validate_json(json_string).model_dump()
    except (APITimeoutError, ValidationError) as e:
        print(f"   > ❌ JSON formatting failed: {e}")
        return Observation(
            status="FAILURE",
            key_finding=f"Server-side observation failed: {type(e).__name__}",
            full_output=truncated_output
        ).model_dump()


# --- API Endpoints (Unchanged from Interactive Model) ---
class SessionRequest(BaseModel): session_id: str


class ExecuteRequest(SessionRequest): command: str


@app.post("/session/start")
def start_session():
    session_id = str(uuid.uuid4())
    print(f"\n--- [START] New session request ---")
    try:
        container = kali_manager.create_container()
        active_sessions[session_id] = container
        print(f"--- ✅ Session '{session_id}' started ---")
        return {"session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create container: {e}")


@app.post("/session/execute")
def execute_in_session(request: ExecuteRequest):
    container = active_sessions.get(request.session_id)
    if not container: raise HTTPException(status_code=404, detail="Session not found.")

    print(f"\n--- [EXECUTE] In session '{request.session_id}': '{request.command}' ---")
    try:
        raw_output = container.send_command_and_get_output(request.command)
        # --- KEY CHANGE: Format the output before returning ---
        json_observation = _format_output_as_json(request.command, raw_output)
        print("--- ✅ Command executed and formatted ---")
        return json_observation  # Return the JSON object directly
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Command execution failed: {e}")


@app.post("/session/end")
def end_session(request: SessionRequest):
    container = active_sessions.pop(request.session_id, None)
    if not container: raise HTTPException(status_code=404, detail="Session not found.")
    print(f"\n--- [END] Session '{request.session_id}' ---")
    container.destroy()
    return {"message": "Session ended."}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=1611)