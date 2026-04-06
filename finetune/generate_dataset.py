"""
Generates a shell command completion dataset for fine-tuning.
For each full command, creates training pairs at every prefix length.

Example: "git status" → 9 pairs:
  "g"        → "it status"
  "gi"       → "t status"
  "git"      → " status"
  "git "     → "status"
  "git s"    → "tatus"
  ...
"""

import json
import random

SYSTEM_PROMPT = (
    "You are a zsh terminal autocomplete. "
    "Output ONLY the raw text that completes the user's input. "
    "No explanation, no markdown, no quotes."
)

# Full commands to learn completions for
COMMANDS = [
    # git
    "git status",
    "git checkout",
    "git checkout -b feature/",
    "git commit -m \"\"",
    "git commit --amend",
    "git add .",
    "git add -A",
    "git push origin main",
    "git push origin",
    "git pull origin main",
    "git pull",
    "git fetch",
    "git fetch --all",
    "git merge",
    "git rebase",
    "git rebase -i HEAD~",
    "git log --oneline",
    "git log --oneline --graph",
    "git diff",
    "git diff --staged",
    "git stash",
    "git stash pop",
    "git stash list",
    "git branch",
    "git branch -a",
    "git branch -d",
    "git clone",
    "git remote -v",
    "git reset --hard HEAD",
    "git reset HEAD~1",
    "git cherry-pick",
    "git tag",
    "git show",
    "git blame",
    "git bisect",

    # docker
    "docker ps",
    "docker ps -a",
    "docker images",
    "docker build -t",
    "docker run -it",
    "docker run -d",
    "docker run --rm",
    "docker stop",
    "docker rm",
    "docker rmi",
    "docker exec -it",
    "docker logs",
    "docker logs -f",
    "docker pull",
    "docker push",
    "docker compose up",
    "docker compose up -d",
    "docker compose down",
    "docker compose build",
    "docker compose logs",
    "docker compose logs -f",
    "docker inspect",
    "docker network ls",
    "docker volume ls",
    "docker system prune",
    "docker stats",

    # npm / node
    "npm install",
    "npm install --save-dev",
    "npm run dev",
    "npm run build",
    "npm run start",
    "npm run test",
    "npm run lint",
    "npm test",
    "npm start",
    "npm init",
    "npm init -y",
    "npm update",
    "npm outdated",
    "npm audit",
    "npm audit fix",
    "npm publish",
    "npx create-react-app",
    "npx create-next-app",
    "npx ts-node",

    # cargo / rust
    "cargo build",
    "cargo build --release",
    "cargo run",
    "cargo run --release",
    "cargo test",
    "cargo check",
    "cargo clean",
    "cargo add",
    "cargo update",
    "cargo fmt",
    "cargo clippy",
    "cargo doc",
    "cargo doc --open",
    "cargo publish",
    "cargo new",
    "cargo init",

    # kubectl
    "kubectl get pods",
    "kubectl get pods -A",
    "kubectl get nodes",
    "kubectl get services",
    "kubectl get deployments",
    "kubectl describe pod",
    "kubectl logs",
    "kubectl logs -f",
    "kubectl exec -it",
    "kubectl apply -f",
    "kubectl delete -f",
    "kubectl scale deployment",
    "kubectl rollout status",
    "kubectl rollout restart",
    "kubectl port-forward",
    "kubectl config get-contexts",
    "kubectl config use-context",
    "kubectl namespace",

    # python
    "python3 -m venv",
    "python3 -m pip install",
    "python3 -m pytest",
    "pip install",
    "pip install -r requirements.txt",
    "pip freeze > requirements.txt",
    "pip list",
    "pip show",
    "pip uninstall",
    "pytest",
    "pytest -v",
    "pytest --cov",

    # filesystem
    "ls -la",
    "ls -lah",
    "ls -lt",
    "cd ..",
    "cd ~",
    "mkdir -p",
    "rm -rf",
    "rm -f",
    "cp -r",
    "mv",
    "find . -name",
    "find . -type f",
    "find . -type d",
    "grep -r",
    "grep -rn",
    "grep -ri",
    "cat",
    "tail -f",
    "tail -n",
    "head -n",
    "wc -l",
    "du -sh",
    "df -h",
    "chmod +x",
    "chmod 755",
    "chown -R",
    "ln -s",
    "tar -xzf",
    "tar -czf",
    "zip -r",
    "unzip",

    # network / ssh
    "curl -fsSL",
    "curl -X POST",
    "curl -H",
    "wget",
    "ssh -i",
    "scp -r",
    "ping",
    "netstat -tulpn",
    "lsof -i",

    # process
    "ps aux",
    "ps aux | grep",
    "kill -9",
    "pkill",
    "top",
    "htop",

    # editors / tools
    "vim",
    "nvim",
    "code .",
    "cat > ",
    "echo",
    "export",
    "source",
    "which",
    "man",
    "history | grep",

    # brew
    "brew install",
    "brew uninstall",
    "brew update",
    "brew upgrade",
    "brew list",
    "brew search",
    "brew info",
    "brew doctor",
]


def make_pairs(full_command: str, min_prefix: int = 1) -> list[dict]:
    """Generate all training pairs for a full command."""
    pairs = []
    for i in range(min_prefix, len(full_command)):
        prefix = full_command[:i]
        suffix = full_command[i:]
        # Skip trivial suffixes (single space)
        if suffix.strip() == "":
            continue
        pairs.append({
            "messages": [
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": f"Complete: {prefix}"},
                {"role": "assistant", "content": suffix},
            ]
        })
    return pairs


def main():
    all_pairs = []
    for cmd in COMMANDS:
        all_pairs.extend(make_pairs(cmd, min_prefix=1))

    random.shuffle(all_pairs)

    # 90% train, 10% eval
    split = int(len(all_pairs) * 0.9)
    train = all_pairs[:split]
    eval_ = all_pairs[split:]

    with open("dataset_train.jsonl", "w") as f:
        for item in train:
            f.write(json.dumps(item) + "\n")

    with open("dataset_eval.jsonl", "w") as f:
        for item in eval_:
            f.write(json.dumps(item) + "\n")

    print(f"Generated {len(train)} training examples, {len(eval_)} eval examples.")
    print(f"Total commands: {len(COMMANDS)}")
    print(f"Sample pair:")
    sample = random.choice(train)
    print(f"  Input:  {sample['messages'][1]['content']}")
    print(f"  Output: {sample['messages'][2]['content']}")


if __name__ == "__main__":
    main()
