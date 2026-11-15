import subprocess
import os
import sys

def run(cmd, env=None):
    print(f"--> {cmd}")
    subprocess.check_call(cmd, shell=True, env=env)

def deploy():
    dist_dir = os.path.abspath("dist_docs")
    if not os.path.exists(dist_dir):
        print("dist_docs does not exist! Run python scripts/build_docs.py first.")
        sys.exit(1)

    temp_index = os.path.abspath(".git/temp_index")
    if os.path.exists(temp_index):
        os.remove(temp_index)

    env = os.environ.copy()
    env["GIT_INDEX_FILE"] = temp_index
    env["GIT_WORK_TREE"] = dist_dir

    try:
        run(f'git add -A "{dist_dir}"', env=env)
        tree = subprocess.check_output("git write-tree", shell=True, env=env).decode().strip()
        print(f"Committed tree: {tree}")
        commit = subprocess.check_output(f'git commit-tree {tree} -m "deploy: update docs with auth, data engine, testing, and model forms"', shell=True, env=env).decode().strip()
        print(f"Created commit: {commit}")
        run(f"git push origin {commit}:refs/heads/gh-pages --force")
        print("Successfully deployed to gh-pages!")
    finally:
        if os.path.exists(temp_index):
            os.remove(temp_index)

if __name__ == "__main__":
    deploy()
