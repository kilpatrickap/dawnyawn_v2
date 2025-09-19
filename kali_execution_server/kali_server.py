# dawnyawn/kali_execution_server/kali_server.py (NEW Ephemeral Version)
import uvicorn
import uuid
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Local Imports
from kali_driver.driver import KaliManager # Assuming KaliManager is adapted for this

# --- Pydantic Models ---
class ExecuteRequest(BaseModel):
    command: str

class ExecuteResponse(BaseModel):
    filename: str
    file_content: str
    error: str = None

app = FastAPI(title="DawnYawn Ephemeral Execution Server")
print("Initializing Kali Docker Manager...")
kali_manager = KaliManager()
print("Kali Docker Manager initialized.")

@app.post("/execute", response_model=ExecuteResponse)
def execute_command(request: ExecuteRequest):
    container = None
    command = request.command
    # Sanitize command to create a valid filename
    sanitized_command = "".join(c for c in command if c.isalnum() or c in (' ', '_')).rstrip()
    output_filename = f"{sanitized_command.replace(' ', '_')}_{uuid.uuid4().hex[:6]}.txt"
    output_filepath_in_container = f"/tmp/{output_filename}"

    print(f"\n--- [EXECUTE] New request for command: '{command}' ---")
    try:
        # a. Create a new container
        container = kali_manager.create_container()

        # b. Send the command, redirecting output to our file
        # c. Wait for completion
        full_command_with_redirect = f"{command} > {output_filepath_in_container} 2>&1"
        container.send_command_and_get_output(full_command_with_redirect, timeout=1800)

        # d/e. Get the output file content from the container
        # The driver would use `docker cp` to pull the file to the server's host, then read it.
        file_content = container.copy_file_from_container(output_filepath_in_container)

        print(f"--- ✅ Command executed, result captured in '{output_filename}' ---")
        return ExecuteResponse(filename=output_filename, file_content=file_content)

    except Exception as e:
        print(f"--- ❌ Execution failed: {e} ---")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # f. Terminate the container
        if container:
            print(f"--- [CLEANUP] Destroying container {container.id[:12]} ---")
            container.destroy()