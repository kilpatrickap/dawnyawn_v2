# dawnyawn/main.py
import os
import argparse
from dotenv import load_dotenv
from agent.task_manager import TaskManager


def main():
    load_dotenv()
    if not os.getenv("OLLAMA_BASE_URL") or not os.getenv("LLM_MODEL"):
        print("FATAL ERROR: OLLAMA_BASE_URL or LLM_MODEL not found in .env file.")
        return

    parser = argparse.ArgumentParser(description="DawnYawn Autonomous Agent")
    parser.add_argument("goal", type=str, help="The high-level goal for the agent.")
    args = parser.parse_args()

    print("--- DawnYawn Agent Initializing ---")
    print("--- Using Local LLM:", os.getenv("LLM_MODEL"), "---")
    print("⚠️  SECURITY WARNING: This agent executes AI-generated commands on a remote server.")

    task_manager = TaskManager(goal=args.goal)
    task_manager.run()


if __name__ == "__main__":
    main()