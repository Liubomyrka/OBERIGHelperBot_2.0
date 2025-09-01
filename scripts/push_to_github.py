import os
import subprocess
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))


def run(cmd):
    subprocess.check_call(cmd, cwd=ROOT_DIR)


def has_changes():
    result = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT_DIR, capture_output=True, text=True)
    return bool(result.stdout.strip())


def main():
    if not has_changes():
        print("No local changes to push.")
        return

    run(["git", "add", "."])
    # Add logs only when explicitly allowed
    log_path = os.path.join(ROOT_DIR, "bot.log")
    if os.path.exists(log_path) and os.getenv("PUSH_LOGS") == "1":
        run(["git", "add", "-f", "bot.log"])
    elif os.path.exists(log_path):
        print("Skipping bot.log (set PUSH_LOGS=1 to include)")
    msg = f"Local sync {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    run(["git", "commit", "-m", msg])
    run(["git", "push"])
    print("Changes pushed to GitHub.")


if __name__ == "__main__":
    main()
