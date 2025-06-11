import os
import subprocess

ROOT_DIR = os.path.dirname(os.path.dirname(__file__))

def run(cmd):
    subprocess.check_call(cmd, cwd=ROOT_DIR)

if __name__ == "__main__":
    run(["git", "pull"])
    print("Repository synchronized from GitHub.")
