"""
Dataset generator v3 — calitate maxima.

Strategie:
1. Comenzi hand-crafted cu argumente REALE pentru tool-uri de baza
   (git, docker, npm, cargo, brew, pip, curl, grep, find, ssh, ls, etc.)
2. Comenzi filtrate din tldr pentru tool-uri specifice
   (kubectl, aws, terraform, gcloud, gh — unde tldr are subcomenzile bine)

Output = comanda COMPLETA (nu sufix) → fara ambiguitate la training.
Prefix-uri la word boundaries + primele caractere.
"""

import json
import re
import random
from pathlib import Path
from itertools import product

SYSTEM_PROMPT = (
    "You are a zsh terminal autocomplete. "
    "Given a partial command, output the complete command on a single line. "
    "No explanation, no markdown, no extra text."
)

random.seed(42)

# ── Argumente realiste ─────────────────────────────────────────────────────────

COMMIT_MESSAGES = [
    "fix authentication bug", "add user registration", "update dependencies",
    "refactor database layer", "fix memory leak", "add unit tests",
    "initial commit", "update README", "fix typo", "add error handling",
    "improve performance", "add logging", "fix null pointer exception",
    "add input validation", "refactor API endpoints", "update configuration",
    "fix race condition", "add pagination", "improve error messages",
    "add caching layer", "fix security vulnerability", "add dark mode",
    "update API documentation", "fix broken tests", "add CI/CD pipeline",
    "remove unused code", "fix cors issue", "add rate limiting",
    "update environment variables", "fix database migration",
]

BRANCH_NAMES = [
    "feature/user-auth", "fix/memory-leak", "chore/update-deps",
    "release/v2.0.0", "feature/dark-mode", "fix/login-bug",
    "feature/api-v2", "hotfix/security-patch", "feature/search",
    "fix/broken-tests", "chore/cleanup", "feature/notifications",
    "fix/cors-issue", "feature/export-csv", "release/v1.5.0",
    "feature/mobile-app", "fix/pagination", "chore/lint-fixes",
    "feature/oauth", "fix/null-pointer",
]

DOCKER_IMAGES = [
    "nginx:latest", "nginx:alpine", "postgres:15", "postgres:14-alpine",
    "redis:alpine", "redis:7", "node:20", "node:18-alpine",
    "python:3.11", "python:3.11-slim", "ubuntu:22.04", "ubuntu:20.04",
    "mysql:8.0", "mongo:7", "rabbitmq:3-management",
    "elasticsearch:8.11.0", "grafana/grafana:latest", "prom/prometheus:latest",
    "traefik:v3.0", "alpine:latest", "golang:1.21", "rust:1.75",
]

CONTAINER_NAMES = [
    "web", "api", "db", "cache", "worker", "nginx", "postgres",
    "redis", "backend", "frontend", "myapp", "app",
]

PORT_MAPPINGS = [
    "3000:3000", "8080:80", "5432:5432", "6379:6379",
    "8000:8000", "443:443", "27017:27017", "5000:5000",
    "9200:9200", "3306:3306",
]

NPM_PACKAGES = [
    "express", "react", "typescript", "lodash", "axios",
    "dotenv", "jest", "eslint", "prettier", "webpack",
    "next", "vue", "svelte", "prisma", "mongoose",
    "zod", "tailwindcss", "vite", "vitest", "fastify",
    "cors", "helmet", "morgan", "nodemon", "ts-node",
    "react-router-dom", "redux", "@types/node", "socket.io",
]

NPM_DEV_PACKAGES = [
    "typescript", "jest", "eslint", "prettier", "@types/node",
    "@types/express", "ts-jest", "nodemon", "vitest", "husky",
    "@testing-library/react", "cypress", "playwright",
]

NPM_SCRIPTS = [
    "dev", "build", "start", "test", "lint", "format",
    "preview", "deploy", "typecheck", "e2e",
]

CARGO_PACKAGES = [
    "serde", "tokio", "reqwest", "clap", "anyhow",
    "thiserror", "tracing", "axum", "sqlx", "diesel",
    "uuid", "chrono", "regex", "rand", "rayon",
    "hyper", "tower", "actix-web", "rocket", "warp",
]

BREW_PACKAGES = [
    "git", "node", "python", "ripgrep", "fd", "fzf",
    "jq", "yq", "wget", "curl", "tmux", "htop",
    "neovim", "bat", "eza", "delta", "lazygit",
    "postgresql", "redis", "mongodb-community",
    "gh", "awscli", "terraform", "kubectl", "helm",
    "ffmpeg", "imagemagick", "openssl", "cmake", "gcc",
    "nvm", "pyenv", "rbenv", "rustup", "go",
]

PIP_PACKAGES = [
    "requests", "flask", "django", "fastapi", "sqlalchemy",
    "pandas", "numpy", "pytest", "black", "ruff",
    "pydantic", "celery", "redis", "boto3", "openai",
    "httpx", "uvicorn", "gunicorn", "alembic", "mypy",
    "rich", "typer", "click", "python-dotenv", "pillow",
]

SSH_HOSTS = [
    "user@192.168.1.100", "admin@10.0.0.1", "deploy@myserver.com",
    "ubuntu@ec2-1-2-3-4.compute.amazonaws.com",
    "root@staging.example.com", "git@github.com",
]

CURL_URLS = [
    "https://api.example.com/users", "https://api.example.com/health",
    "http://localhost:3000/api/v1/users", "http://localhost:8080/health",
    "https://api.github.com/repos/owner/repo",
    "https://jsonplaceholder.typicode.com/posts",
]

GREP_PATTERNS = [
    "TODO", "FIXME", "ERROR", "error", "warning",
    "function", "class", "import", "export", "return",
    "password", "secret", "api_key", "token",
]

GREP_DIRS = [
    ".", "src/", "lib/", "./src", "app/",
]

FILE_PATHS = [
    "main.py", "app.py", "index.js", "main.rs", "main.go",
    "src/main.py", "src/index.ts", "Dockerfile", "docker-compose.yml",
    "README.md", ".env", "package.json", "Cargo.toml", "go.mod",
    "requirements.txt", "pyproject.toml", "tsconfig.json",
]

DIRS = [
    ".", "src/", "dist/", "build/", "tests/", "docs/",
    "~", "~/projects", "~/Desktop", "/tmp",
]

K8S_NAMESPACES = ["default", "production", "staging", "kube-system", "monitoring"]
K8S_RESOURCES = ["pod", "pods", "deployment", "service", "configmap", "secret", "ingress", "node"]
K8S_DEPLOYMENTS = ["web", "api", "worker", "frontend", "backend", "nginx"]

AWS_REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
AWS_PROFILES = ["default", "production", "staging", "dev"]

TERRAFORM_ENVS = ["production", "staging", "dev"]

PYTHON_VERSIONS = ["3.11", "3.12", "3.10", "3.9"]
NODE_VERSIONS = ["20", "18", "16"]

# ── Generator de comenzi ───────────────────────────────────────────────────────

def gen_git() -> list[str]:
    cmds = []

    # git status / diff
    cmds += ["git status", "git status -sb", "git status --short"]
    cmds += ["git diff", "git diff --staged", "git diff HEAD~1", "git diff --stat"]

    # git add
    cmds += ["git add .", "git add -A", "git add -p"]
    for f in FILE_PATHS[:8]:
        cmds.append(f"git add {f}")

    # git commit
    for msg in COMMIT_MESSAGES:
        cmds.append(f'git commit -m "{msg}"')
    cmds += [
        "git commit --amend --no-edit",
        "git commit --amend",
        "git commit -am \"fix typo\"",
        "git commit --allow-empty -m \"trigger CI\"",
    ]

    # git checkout / switch
    for branch in BRANCH_NAMES:
        cmds.append(f"git checkout {branch}")
        cmds.append(f"git checkout -b {branch}")
        cmds.append(f"git switch {branch}")
        cmds.append(f"git switch -c {branch}")

    # git push / pull
    for branch in BRANCH_NAMES[:8]:
        cmds.append(f"git push origin {branch}")
        cmds.append(f"git pull origin {branch}")
    cmds += [
        "git push", "git push --force-with-lease", "git push --tags",
        "git push -u origin main", "git push origin main",
        "git pull", "git pull --rebase", "git pull origin main",
        "git fetch", "git fetch --all", "git fetch --prune",
    ]

    # git merge / rebase
    for branch in BRANCH_NAMES[:6]:
        cmds.append(f"git merge {branch}")
        cmds.append(f"git rebase {branch}")
    cmds += [
        "git merge --no-ff main", "git rebase main",
        "git rebase -i HEAD~3", "git rebase -i HEAD~5",
        "git rebase --abort", "git rebase --continue",
        "git merge --abort",
    ]

    # git log
    cmds += [
        "git log --oneline", "git log --oneline --graph",
        "git log --oneline -10", "git log --oneline --all",
        "git log -p", "git log --stat",
        "git log --oneline --graph --all",
        "git log --format='%h %s' -20",
    ]

    # git branch
    cmds += [
        "git branch", "git branch -a", "git branch -v",
        "git branch -d feature/user-auth", "git branch -D feature/old",
        "git branch -r", "git branch --merged",
    ]

    # git stash
    cmds += [
        "git stash", "git stash pop", "git stash list",
        "git stash apply", "git stash drop", "git stash clear",
        "git stash push -m \"work in progress\"",
    ]

    # git remote
    cmds += [
        "git remote -v", "git remote add origin git@github.com:user/repo.git",
        "git remote remove origin", "git remote rename origin upstream",
    ]

    # git reset
    cmds += [
        "git reset HEAD~1", "git reset --soft HEAD~1",
        "git reset --hard HEAD", "git reset --hard HEAD~1",
        "git reset --mixed HEAD~2",
    ]

    # git tag
    cmds += [
        "git tag v1.0.0", "git tag -a v2.0.0 -m \"Release v2.0.0\"",
        "git tag -l", "git push origin --tags",
        "git tag -d v1.0.0",
    ]

    # git clone
    cmds += [
        "git clone git@github.com:user/repo.git",
        "git clone https://github.com/user/repo.git",
        "git clone --depth=1 https://github.com/user/repo.git",
        "git clone git@github.com:user/repo.git myproject",
    ]

    # misc
    cmds += [
        "git cherry-pick abc1234", "git bisect start",
        "git blame README.md", "git show HEAD",
        "git show HEAD:src/main.py", "git shortlog -sn",
        "git clean -fd", "git clean -fdx",
        "git submodule update --init", "git submodule update --remote",
        "git worktree add ../hotfix hotfix/security",
        "git config --global user.email \"user@example.com\"",
        "git config --global user.name \"John Doe\"",
        "git config --list",
    ]

    return cmds


def gen_docker() -> list[str]:
    cmds = []

    # docker ps
    cmds += ["docker ps", "docker ps -a", "docker ps -q", "docker ps --format '{{.Names}}'"]

    # docker images
    cmds += ["docker images", "docker images -a", "docker image ls", "docker image prune"]

    # docker pull / push
    for img in DOCKER_IMAGES[:10]:
        cmds.append(f"docker pull {img}")
    for img in DOCKER_IMAGES[:5]:
        cmds.append(f"docker push {img}")

    # docker run
    for img in DOCKER_IMAGES[:8]:
        cmds.append(f"docker run -it {img}")
        cmds.append(f"docker run -d {img}")
        cmds.append(f"docker run --rm {img}")
    for port, img in zip(PORT_MAPPINGS[:6], DOCKER_IMAGES[:6]):
        cmds.append(f"docker run -d -p {port} {img}")
    for name, img in zip(CONTAINER_NAMES[:6], DOCKER_IMAGES[:6]):
        cmds.append(f"docker run -d --name {name} {img}")
    cmds += [
        "docker run -it --rm ubuntu:22.04 bash",
        "docker run -d -p 8080:80 --name web nginx:alpine",
        "docker run --rm -v $(pwd):/app node:20 npm install",
        "docker run -e NODE_ENV=production -p 3000:3000 myapp",
    ]

    # docker exec
    for name in CONTAINER_NAMES[:6]:
        cmds.append(f"docker exec -it {name} bash")
        cmds.append(f"docker exec -it {name} sh")
    cmds += [
        "docker exec -it web nginx -t",
        "docker exec -it db psql -U postgres",
    ]

    # docker stop / rm
    for name in CONTAINER_NAMES[:6]:
        cmds.append(f"docker stop {name}")
        cmds.append(f"docker rm {name}")
        cmds.append(f"docker rm -f {name}")

    # docker logs
    for name in CONTAINER_NAMES[:6]:
        cmds.append(f"docker logs {name}")
        cmds.append(f"docker logs -f {name}")
        cmds.append(f"docker logs --tail 100 {name}")

    # docker build
    cmds += [
        "docker build -t myapp .",
        "docker build -t myapp:latest .",
        "docker build -t myapp:v1.0.0 .",
        "docker build --no-cache -t myapp .",
        "docker build -f Dockerfile.prod -t myapp .",
        "docker buildx build --platform linux/amd64 -t myapp .",
    ]

    # docker compose
    cmds += [
        "docker compose up", "docker compose up -d",
        "docker compose up --build", "docker compose up -d --build",
        "docker compose down", "docker compose down -v",
        "docker compose ps", "docker compose logs",
        "docker compose logs -f", "docker compose logs -f web",
        "docker compose build", "docker compose restart",
        "docker compose exec web bash", "docker compose exec db psql -U postgres",
        "docker compose pull", "docker compose stop",
    ]

    # docker system
    cmds += [
        "docker system prune", "docker system prune -a",
        "docker system df", "docker volume ls",
        "docker volume prune", "docker network ls",
        "docker network inspect bridge",
        "docker inspect web", "docker stats",
        "docker stats --no-stream",
    ]

    return cmds


def gen_npm() -> list[str]:
    cmds = []

    # npm install
    cmds += [
        "npm install", "npm install --save-dev", "npm ci",
        "npm install --production", "npm install --legacy-peer-deps",
    ]
    for pkg in NPM_PACKAGES[:12]:
        cmds.append(f"npm install {pkg}")
    for pkg in NPM_DEV_PACKAGES[:8]:
        cmds.append(f"npm install --save-dev {pkg}")

    # npm run
    for script in NPM_SCRIPTS:
        cmds.append(f"npm run {script}")
    cmds += ["npm start", "npm test", "npm publish"]

    # npm misc
    cmds += [
        "npm init -y", "npm init", "npm update",
        "npm outdated", "npm audit", "npm audit fix",
        "npm audit fix --force", "npm list", "npm list --depth=0",
        "npm uninstall express", "npm cache clean --force",
        "npm version patch", "npm version minor", "npm version major",
    ]

    # npx
    cmds += [
        "npx create-react-app myapp",
        "npx create-next-app myapp",
        "npx create-vite myapp --template react-ts",
        "npx prisma migrate dev",
        "npx prisma generate",
        "npx prisma studio",
        "npx ts-node src/index.ts",
        "npx eslint --fix src/",
        "npx prettier --write .",
        "npx playwright install",
    ]

    # yarn / pnpm
    cmds += [
        "yarn", "yarn install", "yarn add express",
        "yarn add --dev typescript", "yarn build",
        "yarn dev", "yarn test", "yarn lint",
        "pnpm install", "pnpm add express",
        "pnpm add --save-dev typescript", "pnpm run dev",
        "pnpm run build", "pnpm update",
    ]

    return cmds


def gen_cargo() -> list[str]:
    cmds = []

    # build / run
    cmds += [
        "cargo build", "cargo build --release",
        "cargo run", "cargo run --release",
        "cargo run -- --help", "cargo run --example basic",
    ]

    # test
    cmds += [
        "cargo test", "cargo test --release",
        "cargo test -- --nocapture",
        "cargo test integration_tests",
        "cargo test --lib", "cargo test --doc",
    ]

    # check / lint
    cmds += [
        "cargo check", "cargo clippy",
        "cargo clippy --all-targets",
        "cargo clippy -- -D warnings",
        "cargo fmt", "cargo fmt --check",
    ]

    # add packages
    for pkg in CARGO_PACKAGES:
        cmds.append(f"cargo add {pkg}")
    cmds += [
        "cargo add tokio --features full",
        "cargo add serde --features derive",
        "cargo add clap --features derive",
        "cargo add sqlx --features postgres,runtime-tokio",
    ]

    # misc
    cmds += [
        "cargo update", "cargo clean", "cargo doc",
        "cargo doc --open", "cargo doc --no-deps",
        "cargo new myproject", "cargo new --lib mylib",
        "cargo init", "cargo init --lib",
        "cargo publish", "cargo publish --dry-run",
        "cargo bench", "cargo tree",
        "cargo search tokio", "cargo install cargo-watch",
        "cargo install cargo-edit", "cargo watch -x run",
        "cargo watch -x test", "cargo expand",
    ]

    return cmds


def gen_brew() -> list[str]:
    cmds = []

    for pkg in BREW_PACKAGES:
        cmds.append(f"brew install {pkg}")
        cmds.append(f"brew uninstall {pkg}")

    cmds += [
        "brew update", "brew upgrade", "brew upgrade --greedy",
        "brew list", "brew list --cask",
        "brew search node", "brew search python",
        "brew info git", "brew info node",
        "brew doctor", "brew cleanup",
        "brew tap homebrew/cask-fonts",
        "brew install --cask visual-studio-code",
        "brew install --cask docker",
        "brew install --cask iterm2",
        "brew install --cask firefox",
        "brew outdated", "brew pin node",
        "brew services list", "brew services start postgresql",
        "brew services stop postgresql", "brew services restart redis",
        "brew link node", "brew unlink node",
    ]

    return cmds


def gen_pip() -> list[str]:
    cmds = []

    for pkg in PIP_PACKAGES:
        cmds.append(f"pip install {pkg}")
        cmds.append(f"pip3 install {pkg}")

    cmds += [
        "pip install -r requirements.txt",
        "pip install -r requirements-dev.txt",
        "pip install -e .",
        "pip install --upgrade pip",
        "pip install --upgrade setuptools wheel",
        "pip freeze > requirements.txt",
        "pip freeze", "pip list", "pip list --outdated",
        "pip show requests", "pip show flask",
        "pip uninstall requests",
        "pip install requests==2.31.0",
        "pip install django>=4.0",
        "pip cache purge",
        "python -m pip install --upgrade pip",
        "python3 -m venv venv",
        "python3 -m venv .venv",
        "python -m pytest", "python -m pytest -v",
        "python -m pytest --cov=src",
        "python -m black .", "python -m ruff check .",
        "python -m mypy src/",
    ]

    return cmds


def gen_curl() -> list[str]:
    cmds = []

    for url in CURL_URLS:
        cmds.append(f"curl {url}")
        cmds.append(f"curl -s {url}")
        cmds.append(f"curl -v {url}")
        cmds.append(f"curl -X POST {url}")
        cmds.append(f"curl -X DELETE {url}")
        cmds.append(f"curl -H 'Content-Type: application/json' {url}")
        cmds.append(f"curl -H 'Authorization: Bearer mytoken' {url}")
        cmds.append(f"curl -X POST -H 'Content-Type: application/json' -d '{{\"key\":\"value\"}}' {url}")
        cmds.append(f"curl -o output.json {url}")

    cmds += [
        "curl -fsSL https://example.com/install.sh | bash",
        "curl -I https://example.com",
        "curl --head https://example.com",
        "curl -L https://example.com",
        "curl -u user:password https://api.example.com",
        "curl --insecure https://localhost:8443",
        "curl -w '%{http_code}' -o /dev/null https://api.example.com",
    ]

    return cmds


def gen_ssh() -> list[str]:
    cmds = []

    for host in SSH_HOSTS:
        cmds.append(f"ssh {host}")
        cmds.append(f"ssh -p 22 {host}")

    cmds += [
        "ssh -i ~/.ssh/id_rsa user@192.168.1.100",
        "ssh -i ~/.ssh/mykey.pem ubuntu@ec2-1-2-3-4.compute.amazonaws.com",
        "ssh -L 8080:localhost:80 user@192.168.1.100",
        "ssh -R 9090:localhost:9090 user@myserver.com",
        "ssh -N -f -L 5432:localhost:5432 user@db.example.com",
        "ssh-keygen -t ed25519 -C \"user@example.com\"",
        "ssh-keygen -t rsa -b 4096 -C \"user@example.com\"",
        "ssh-copy-id user@192.168.1.100",
        "ssh-add ~/.ssh/id_rsa",
        "ssh-add -l",
        "scp file.txt user@192.168.1.100:/home/user/",
        "scp -r src/ user@192.168.1.100:/var/www/",
        "scp user@192.168.1.100:/var/log/app.log ./",
        "rsync -avz src/ user@192.168.1.100:/var/www/",
        "rsync -avz --delete dist/ user@myserver.com:/var/www/html/",
        "rsync -avzn src/ dest/",
    ]

    return cmds


def gen_filesystem() -> list[str]:
    cmds = []

    # ls
    cmds += [
        "ls", "ls -la", "ls -lah", "ls -lt", "ls -ltr",
        "ls -la src/", "ls -la ~/projects",
        "ls *.json", "ls -la | grep .py",
    ]

    # cd / mkdir / rm
    cmds += [
        "cd ..", "cd ~", "cd -", "cd ~/projects",
        "mkdir myproject", "mkdir -p src/components",
        "mkdir -p dist/assets", "mkdir -p ~/.config/app",
        "rm -rf dist/", "rm -rf node_modules/",
        "rm -rf .cache/", "rm file.txt",
        "rm -f file.txt", "rm *.log",
    ]

    # cp / mv
    for f in FILE_PATHS[:6]:
        cmds.append(f"cp {f} {f}.bak")
        cmds.append(f"mv {f} /tmp/{f}")
    cmds += [
        "cp -r src/ dist/", "cp -r . ../backup/",
        "mv file.txt ../",  "mv old.py new.py",
    ]

    # find
    cmds += [
        "find . -name '*.py'", "find . -name '*.js'",
        "find . -name '*.ts'", "find . -name '*.json'",
        "find . -type f -name '*.log'",
        "find . -type d -name '__pycache__'",
        "find . -name '*.py' -not -path './venv/*'",
        "find . -mtime -1 -type f",
        "find /var/log -name '*.log' -size +10M",
        "find . -empty -type f",
        "find . -name '.DS_Store' -delete",
        "find . -name '*.py' -exec wc -l {} +",
    ]

    # grep
    for pattern in GREP_PATTERNS[:8]:
        cmds.append(f"grep -r \"{pattern}\" .")
        cmds.append(f"grep -rn \"{pattern}\" src/")
        cmds.append(f"grep -ri \"{pattern}\" .")
    cmds += [
        "grep -r \"TODO\" . --include='*.py'",
        "grep -r \"TODO\" . --include='*.ts'",
        "grep -rn \"console.log\" src/",
        "grep -l \"import\" src/",
        "grep -c \"error\" app.log",
    ]

    # cat / tail / head
    cmds += [
        "cat README.md", "cat package.json", "cat .env",
        "tail -f /var/log/nginx/access.log",
        "tail -f /var/log/app.log",
        "tail -n 100 app.log", "tail -n 50 error.log",
        "head -n 20 README.md", "head -n 50 data.csv",
    ]

    # chmod / chown
    cmds += [
        "chmod +x script.sh", "chmod 755 script.sh",
        "chmod 644 config.yml", "chmod -R 755 dist/",
        "chown -R www-data:www-data /var/www/",
        "chown user:staff file.txt",
    ]

    # tar / zip
    cmds += [
        "tar -czf archive.tar.gz src/",
        "tar -czf backup.tar.gz dist/",
        "tar -xzf archive.tar.gz",
        "tar -xzf archive.tar.gz -C /tmp/",
        "tar -tvf archive.tar.gz",
        "zip -r archive.zip src/",
        "zip -r dist.zip dist/",
        "unzip archive.zip",
        "unzip archive.zip -d /tmp/",
    ]

    # misc
    cmds += [
        "wc -l src/main.py", "wc -l *.py",
        "du -sh .", "du -sh node_modules/",
        "df -h", "df -h /",
        "ln -s /usr/local/bin/python3 /usr/local/bin/python",
        "touch .env", "touch README.md",
        "which python3", "which node", "which git",
        "echo $PATH", "echo $HOME",
        "export NODE_ENV=production",
        "export PATH=$PATH:/usr/local/bin",
        "source .env", "source venv/bin/activate",
        "source ~/.zshrc",
    ]

    return cmds


def gen_process() -> list[str]:
    cmds = []
    cmds += [
        "ps aux", "ps aux | grep node", "ps aux | grep python",
        "ps -ef", "top", "htop",
        "kill -9 1234", "kill 1234",
        "pkill node", "pkill python", "pkill -f myapp",
        "killall node",
        "lsof -i :3000", "lsof -i :8080", "lsof -i :5432",
        "lsof -i tcp", "lsof -p 1234",
        "netstat -tulpn", "ss -tulpn",
        "nohup python app.py &",
        "nice -n 10 ./heavy_process",
    ]
    return cmds


def gen_git_extended() -> list[str]:
    """Comenzi git mai avansate."""
    cmds = []
    cmds += [
        "git reflog", "git reflog --oneline",
        "git config --global init.defaultBranch main",
        "git config --global pull.rebase true",
        "git config --global core.editor nvim",
        "git mv old.py new.py",
        "git archive --format=zip HEAD > release.zip",
        "git grep \"TODO\"",
        "git log --author=\"John\" --oneline",
        "git log --since=\"2024-01-01\" --oneline",
        "git diff main..feature/user-auth",
        "git stash push -m \"wip: user auth\" src/auth.py",
        "git apply patch.diff",
        "git format-patch HEAD~3",
        "git am patches/*.patch",
        "git notes add -m \"reviewed\" HEAD",
        "git tag -a v2.0.0 -m \"Release v2.0.0\" HEAD",
        "git push origin v2.0.0",
        "git push origin :feature/old-branch",
        "git remote set-url origin git@github.com:user/newrepo.git",
    ]
    return cmds


def gen_system_tools() -> list[str]:
    cmds = []
    cmds += [
        # make
        "make", "make build", "make test", "make clean",
        "make install", "make all", "make help",
        "make -j4", "make -j8",

        # environment
        "env", "printenv", "printenv PATH",
        "export DEBUG=true", "export PORT=3000",
        "unset DEBUG",

        # history
        "history", "history | grep git", "history | grep docker",
        "history -c",

        # which / type
        "which python3", "which node", "which cargo",
        "type git", "command -v node",

        # man / help
        "man git", "man curl", "man ssh",

        # misc
        "date", "date +%Y-%m-%d",
        "uptime", "uname -a", "uname -m",
        "whoami", "id", "groups",
        "hostname", "pwd",
        "clear", "reset",
        "sleep 5", "wait",
        "xargs", "xargs -I {} echo {}",
        "sort file.txt", "sort -r file.txt", "sort -n numbers.txt",
        "uniq", "uniq -c", "uniq -d",
        "cut -d',' -f1 data.csv", "cut -d':' -f1 /etc/passwd",
        "awk '{print $1}' file.txt", "awk -F',' '{print $2}' data.csv",
        "sed 's/old/new/g' file.txt", "sed -i 's/old/new/g' file.txt",
        "tr '[:upper:]' '[:lower:]' < file.txt",
        "base64 -d encoded.txt", "base64 file.txt",
        "md5 file.txt", "shasum -a 256 file.txt",
        "openssl rand -hex 32", "openssl genrsa -out key.pem 2048",
        "jq '.' data.json", "jq '.items[]' data.json",
        "jq '.name' package.json", "jq -r '.version' package.json",
    ]
    return cmds


def gen_cloud() -> list[str]:
    cmds = []

    # kubectl
    for resource in K8S_RESOURCES:
        cmds.append(f"kubectl get {resource}")
        cmds.append(f"kubectl get {resource} -A")
    for ns in K8S_NAMESPACES[:3]:
        cmds.append(f"kubectl get pods -n {ns}")
        cmds.append(f"kubectl get deployments -n {ns}")
    for dep in K8S_DEPLOYMENTS[:4]:
        cmds.append(f"kubectl describe deployment {dep}")
        cmds.append(f"kubectl logs deployment/{dep}")
        cmds.append(f"kubectl logs -f deployment/{dep}")
        cmds.append(f"kubectl exec -it deployment/{dep} -- bash")
        cmds.append(f"kubectl rollout restart deployment/{dep}")
        cmds.append(f"kubectl rollout status deployment/{dep}")
        cmds.append(f"kubectl scale deployment {dep} --replicas=3")
    cmds += [
        "kubectl apply -f deployment.yml",
        "kubectl apply -f k8s/",
        "kubectl delete -f deployment.yml",
        "kubectl port-forward pod/mypod 8080:80",
        "kubectl port-forward svc/myservice 3000:3000",
        "kubectl config get-contexts",
        "kubectl config use-context production",
        "kubectl config current-context",
        "kubectl top pods", "kubectl top nodes",
        "kubectl describe node mynode",
        "kubectl get events --sort-by=.lastTimestamp",
        "kubectl create namespace production",
        "kubectl delete namespace staging",
    ]

    # terraform
    cmds += [
        "terraform init", "terraform plan",
        "terraform plan -out=tfplan", "terraform apply",
        "terraform apply tfplan", "terraform apply -auto-approve",
        "terraform destroy", "terraform destroy -auto-approve",
        "terraform validate", "terraform fmt",
        "terraform fmt -recursive", "terraform output",
        "terraform state list", "terraform state show",
        "terraform import", "terraform workspace list",
        "terraform workspace new production",
        "terraform workspace select production",
    ]

    # gh (GitHub CLI)
    cmds += [
        "gh pr list", "gh pr view", "gh pr create",
        "gh pr create --title \"feat: add user auth\" --body \"description\"",
        "gh pr merge", "gh pr review --approve",
        "gh pr checkout 123",
        "gh issue list", "gh issue create",
        "gh issue view 42",
        "gh repo clone user/repo",
        "gh repo create myrepo --public",
        "gh workflow run ci.yml",
        "gh workflow list", "gh run list",
        "gh run view 123", "gh run watch",
        "gh release create v1.0.0",
        "gh release list",
        "gh auth login", "gh auth status",
        "gh api repos/owner/repo",
    ]

    return cmds


# ── tldr filtered pentru comenzi specifice ────────────────────────────────────

TLDR_ALLOWED_FOR_SUPPLEMENT = {
    "aws", "az", "gcloud", "systemctl", "journalctl",
    "conda", "uv", "helm", "podman",
}

PLACEHOLDER_RE = re.compile(r'\{\{.*?\}\}')

REPLACEMENTS = {
    r'\{\{file(name)?\}\}': 'file.txt',
    r'\{\{directory\}\}': 'mydir',
    r'\{\{path(/to/.*?)?\}\}': '/path/to/file',
    r'\{\{image\}\}': 'ubuntu:latest',
    r'\{\{container\}\}': 'mycontainer',
    r'\{\{port\}\}': '8080',
    r'\{\{host(name)?\}\}': 'example.com',
    r'\{\{user(name)?\}\}': 'myuser',
    r'\{\{branch\}\}': 'main',
    r'\{\{remote\}\}': 'origin',
    r'\{\{tag\}\}': 'v1.0.0',
    r'\{\{commit\}\}': 'abc1234',
    r'\{\{message\}\}': '"fix bug"',
    r'\{\{package\}\}': 'mypackage',
    r'\{\{version\}\}': '1.0.0',
    r'\{\{url\}\}': 'https://example.com',
    r'\{\{ip(_address)?\}\}': '192.168.1.1',
    r'\{\{name\}\}': 'myproject',
    r'\{\{namespace\}\}': 'default',
    r'\{\{pod\}\}': 'mypod',
    r'\{\{deployment\}\}': 'myapp',
    r'\{\{service\}\}': 'myservice',
    r'\{\{region\}\}': 'us-east-1',
    r'\{\{bucket\}\}': 'mybucket',
    r'\{\{profile\}\}': 'default',
    r'\{\{resource\}\}': 'pods',
    r'\{\{number\}\}': '10',
    r'\{\{count\}\}': '5',
    r'\{\{env(ironment)?\}\}': 'production',
    r'\{\{variable\}\}': 'MY_VAR',
    r'\{\{database\}\}': 'mydb',
    r'\{\{server\}\}': 'db.example.com',
    r'\{\{interface\}\}': 'eth0',
    r'\{\{source\}\}': 'src',
    r'\{\{destination\}\}': 'dest',
    r'\{\{format\}\}': 'json',
    r'\{\{type\}\}': 'file',
    r'\{\{prefix\}\}': 'app',
    r'\{\{role\}\}': 'admin',
    r'\{\{label\}\}': 'app=myapp',
    r'\{\{replicas?\}\}': '3',
    r'\{\{key\}\}': 'mykey',
    r'\{\{value\}\}': 'myvalue',
    r'\{\{size\}\}': '100M',
    r'\{\{seconds\}\}': '30',
    r'\{\{mode\}\}': '755',
    r'\{\{output\}\}': 'output.txt',
}


def clean_tldr_command(cmd: str) -> str | None:
    cmd = cmd.strip()
    if cmd.startswith(('#', '-', '>', '!', '|')):
        return None

    for pattern, replacement in REPLACEMENTS.items():
        cmd = re.sub(pattern, replacement, cmd, flags=re.IGNORECASE)
    cmd = PLACEHOLDER_RE.sub('myvalue', cmd)
    cmd = re.sub(r'\s+', ' ', cmd).strip()

    if len(cmd) < 5 or len(cmd) > 75:
        return None
    if '|' in cmd or '>' in cmd or '<' in cmd:
        return None
    if '`' in cmd or '$(' in cmd:
        return None
    # Zero toleranta pentru placeholder-e ramase
    if 'myvalue' in cmd or '/path/to/file' in cmd:
        return None
    if re.search(r'\bvalue\b', cmd):
        return None

    bad = ['SELECT', 'FROM', 'WHERE', 'INSERT', 'function(', 'return ']
    if any(b in cmd for b in bad):
        return None

    words = cmd.split()
    tool = words[1] if words[0] == 'sudo' and len(words) > 1 else words[0]
    if tool not in TLDR_ALLOWED_FOR_SUPPLEMENT:
        return None

    return cmd


def load_tldr_supplement() -> list[str]:
    cmds = []
    for dir_path in ["tldr/pages/common", "tldr/pages/linux", "tldr/pages/osx"]:
        path = Path(dir_path)
        if not path.exists():
            continue
        for f in path.glob("*.md"):
            try:
                text = f.read_text(encoding='utf-8')
            except Exception:
                continue
            for line in text.split('\n'):
                line = line.strip()
                if line.startswith('`') and line.endswith('`'):
                    cmd = clean_tldr_command(line[1:-1])
                    if cmd:
                        cmds.append(cmd)
    return list(dict.fromkeys(cmds))


# ── Prefix generation ──────────────────────────────────────────────────────────

def get_prefix_positions(cmd: str) -> list[int]:
    positions = set()
    words = cmd.split()

    # Primele 2-5 caractere
    for i in range(2, min(6, len(cmd))):
        positions.add(i)

    # Word boundaries
    pos = 0
    for word in words[:-1]:
        pos += len(word) + 1
        if 2 <= pos < len(cmd):
            positions.add(pos)

    # Primele 1-3 litere din fiecare cuvant
    pos = 0
    for word in words:
        for offset in range(1, 4):
            p = pos + offset
            if 2 <= p < len(cmd):
                positions.add(p)
        pos += len(word) + 1

    return sorted(p for p in positions if 2 <= p < len(cmd))


def make_pairs(cmd: str) -> list[dict]:
    pairs = []
    for pos in get_prefix_positions(cmd):
        prefix = cmd[:pos]
        pairs.append({
            "messages": [
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": prefix},
                {"role": "assistant", "content": cmd},
            ]
        })
    return pairs


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Generare dataset v3...")

    # 1. Comenzi hand-crafted
    handcrafted = []
    generators = [
        ("git", gen_git),
        ("git extended", gen_git_extended),
        ("docker", gen_docker),
        ("npm/node", gen_npm),
        ("cargo", gen_cargo),
        ("brew", gen_brew),
        ("pip/python", gen_pip),
        ("curl", gen_curl),
        ("ssh/scp", gen_ssh),
        ("filesystem", gen_filesystem),
        ("process", gen_process),
        ("system tools", gen_system_tools),
        ("cloud/k8s/tf/gh", gen_cloud),
    ]

    for name, gen_fn in generators:
        cmds = gen_fn()
        handcrafted.extend(cmds)
        print(f"  [{name}]: {len(cmds)} comenzi")

    handcrafted = list(dict.fromkeys(handcrafted))  # dedup
    print(f"\nTotal hand-crafted: {len(handcrafted)} comenzi unice")

    # 2. Supplement din tldr (doar aws, az, gcloud, systemctl, etc.)
    tldr_cmds = load_tldr_supplement()
    print(f"tldr supplement: {len(tldr_cmds)} comenzi")

    # 3. Combinam
    all_commands = list(dict.fromkeys(handcrafted + tldr_cmds))
    print(f"Total comenzi unice: {len(all_commands)}")

    # 4. Generam perechile
    all_pairs = []
    for cmd in all_commands:
        all_pairs.extend(make_pairs(cmd))

    print(f"Total perechi training: {len(all_pairs)}")

    # 5. Shuffle si split
    random.shuffle(all_pairs)
    split = int(len(all_pairs) * 0.9)
    train = all_pairs[:split]
    eval_ = all_pairs[split:]

    with open("dataset_train_v3.jsonl", "w") as f:
        for item in train:
            f.write(json.dumps(item) + "\n")

    with open("dataset_eval_v3.jsonl", "w") as f:
        for item in eval_:
            f.write(json.dumps(item) + "\n")

    print(f"\nSalvat: {len(train)} train + {len(eval_)} eval")

    # 6. Preview
    print("\n" + "="*60)
    print("PREVIEW — 25 exemple random:")
    print("="*60)
    samples = random.sample(train, 25)
    for s in samples:
        prefix = s['messages'][1]['content']
        full   = s['messages'][2]['content']
        print(f"  '{prefix}'")
        print(f"  → '{full}'")
        print()


if __name__ == "__main__":
    main()
