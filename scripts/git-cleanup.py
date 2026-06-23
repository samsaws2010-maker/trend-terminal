import subprocess
import os

path = "/home/runner/workspace"

# Remove large files from git tracking
files = ["zilaIr9x", "zipFile.zip", "trend-terminal-full.zip", "trend-terminal.zip", "trend-terminal.tar.gz"]
for f in files:
    subprocess.run(["git", "rm", "--cached", f], cwd=path)

# Stage .gitignore
subprocess.run(["git", "add", ".gitignore"], cwd=path)

# Commit
result = subprocess.run(
    ["git", "commit", "-m", "Remove large binary files from git to fix deployment image size"],
    cwd=path,
    capture_output=True,
    text=True
)
print(result.stdout)
print(result.stderr)
