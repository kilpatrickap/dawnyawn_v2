# dawnyawn/main.py (Updated Version)
import os
import argparse
import logging
from dotenv import load_dotenv
from agent.task_manager import TaskManager

# NEW: Function to set up structured logging
def setup_logging():
    """Configures logging to a file and to the console."""
    # Create a 'logs' directory at the project root if it doesn't exist
    project_root = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(project_root, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    log_filepath = os.path.join(logs_dir, 'agent_run.log')

    # Configure the root logger
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [%(name)s] - %(message)s",
        handlers=[
            logging.FileHandler(log_filepath),
            logging.StreamHandler()  # Also log to the console
        ]
    )

def main():
    # Set up logging as the first step
    setup_logging()

    load_dotenv()
    if not os.getenv("OLLAMA_BASE_URL") or not os.getenv("LLM_MODEL"):
        logging.critical("FATAL ERROR: OLLAMA_BASE_URL or LLM_MODEL not found in .env file. Agent cannot start.")
        return

    parser = argparse.ArgumentParser(description="DawnYawn Autonomous Agent")
    parser.add_argument("goal", type=str, help="The high-level goal for the agent.")
    args = parser.parse_args()

    # Replace previous print statements with structured logging
    logging.info("--- DawnYawn Agent Initializing ---")
    logging.info("--- Using Local LLM: %s ---", os.getenv("LLM_MODEL"))
    logging.warning("SECURITY WARNING: This agent executes AI-generated commands on a remote server.")

    try:
        # Initialize and run the main agent controller
        task_manager = TaskManager(goal=args.goal)
        task_manager.run()
        logging.info("--- Mission Concluded ---")
    except Exception as e:
        # A top-level exception handler to catch any unexpected errors from the agent's run
        logging.critical("An unhandled exception occurred during the mission: %s", e, exc_info=True)


if __name__ == "__main__":
    main()