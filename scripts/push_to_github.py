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
    log_path = os.path.join(ROOT_DIR, "bot.log")
    if os.path.exists(log_path):
        run(["git", "add", "-f", "bot.log"])
    msg = f"Local sync {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    run(["git", "commit", "-m", msg])
    run(["git", "push"])
    print("Changes pushed to GitHub.")


if __name__ == "__main__":
    main()
