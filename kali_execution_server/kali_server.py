# kali_execution_server/kali_server.py (Updated Ephemeral Version)
import uvicorn
import uuid
import os
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Local Imports
# NOTE: Your KaliManager/KaliContainer in the driver will need a method to copy files out.
from kali_driver.driver import KaliManager, KaliContainer


# --- Pydantic Models for the new stateless endpoint ---
class ExecuteRequest(BaseModel):
    command: str


class ExecuteResponse(BaseModel):
    filename: str
    file_content: str


# --- FastAPI App Setup ---
app = FastAPI(title="DawnYawn Ephemeral Execution Server")
# Configure logging for the server
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] (ExecutionServer) - %(message)s")

logging.info("Initializing Kali Docker Manager...")
kali_manager = KaliManager()
logging.info("Kali Docker Manager initialized.")


@app.post("/execute", response_model=ExecuteResponse)
def execute_command(request: ExecuteRequest):
    """
    Creates a new container, runs a single command, extracts the output
    to a file, and destroys the container.
    """
    container = None
    command = request.command

    # Sanitize the command to create a valid and safe filename prefix
    sanitized_command = "".join(c for c in command if c.isalnum() or c in (' ', '_', '-')).rstrip()
    unique_id = uuid.uuid4().hex[:6]
    output_filename = f"{sanitized_command.replace(' ', '_')}_{unique_id}.txt"
    output_filepath_in_container = f"/tmp/{output_filename}"

    logging.info("--- [EXECUTE] New request for command: '%s' ---", command)
    try:
        # Step 1: Create a new, isolated container
        container = kali_manager.create_container()
        logging.info("Created temporary container: %s", container.id[:12])

        # Step 2: Construct and send the command to redirect all output to our file
        # The '2>&1' part ensures both stdout and stderr are captured.
        full_command_with_redirect = f"{command} > {output_filepath_in_container} 2>&1"
        container.send_command_and_get_output(full_command_with_redirect, timeout=1800)

        # Step 3: Copy the generated output file from the container
        # This assumes your driver has a method like `copy_file_from_container`.
        file_content = container.copy_file_from_container(output_filepath_in_container)

        logging.info("--- ✅ Command executed, result captured in '%s' ---", output_filename)
        return ExecuteResponse(filename=output_filename, file_content=file_content)

    except Exception as e:
        logging.error("--- ❌ Command execution failed: %s ---", e, exc_info=True)
        # Raise an HTTP exception to send a proper error response back to the agent.
        raise HTTPException(status_code=500, detail=f"Command execution failed on server: {e}")
    finally:
        # Step 4: ALWAYS ensure the container is destroyed to prevent resource leaks.
        if container:
            logging.info("--- [CLEANUP] Destroying container %s ---", container.id[:12])
            container.destroy()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=1611)