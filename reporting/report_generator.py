# dawnyawn/reporting/report_generator.py (NEW FILE)
import os
import json
from datetime import datetime
from typing import List, Dict

def create_report(goal: str, history: List[Dict]):
    """Generates a professional text report from the mission history."""
    REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
    os.makedirs(REPORTS_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_filename = f"report_{timestamp}.txt"
    report_filepath = os.path.join(REPORTS_DIR, report_filename)

    with open(report_filepath, 'w', encoding='utf-8') as f:
        f.write("--- DAWNYAWN MISSION REPORT ---\n")
        f.write("="*35 + "\n\n")
        f.write(f"Mission Goal: {goal}\n")
        f.write(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write("--- EXECUTION LOG ---\n")
        f.write("="*21 + "\n\n")

        for i, item in enumerate(history):
            f.write(f"Step {i + 1}:\n")
            f.write("-" * 10 + "\n")
            f.write(f"  Action Command:\n    `{item['command']}`\n\n")
            f.write("  Observation:\n")
            # Check if observation is JSON-like string and pretty print, otherwise print raw
            try:
                # This part is for the old model; for the new one, it's just text
                obs_text = item.get('observation', 'No observation.')
                f.write("    " + obs_text.replace('\n', '\n    ')) # Indent observation
            except (json.JSONDecodeError, AttributeError):
                 f.write(f"    {item.get('observation', 'No observation.')}\n")
            f.write("\n\n")

        # Extract final finding if available
        final_finding = "Mission did not conclude with a final finding."
        if history and history[-1]['command'] == 'finish_mission':
            final_finding = history[-1]['observation'].get('key_finding', final_finding)

        f.write("--- FINAL SUMMARY ---\n")
        f.write("="*21 + "\n\n")
        f.write(f"{final_finding}\n")

    print(f"\n✅ Professional report generated at: {report_filepath}")
