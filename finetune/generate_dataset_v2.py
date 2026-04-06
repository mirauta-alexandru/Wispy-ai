"""
Dataset generator v2 — bazat pe tldr-pages.
Sursa: comenzi reale din tldr/pages/common + osx + linux

Strategia:
- Output = comanda COMPLETA (nu sufixul) → fara ambiguitate
- Prefix-uri la word boundaries + cateva pozitii intermediare
- Filtram comenzi prea lungi, prea scurte, cu placeholder-e complexe
"""

import json
import re
import random
from pathlib import Path

SYSTEM_PROMPT = (
    "You are a zsh terminal autocomplete. "
    "Given a partial command, output the complete command on a single line. "
    "No explanation, no markdown, no extra text."
)

TLDR_DIRS = [
    "tldr/pages/common",
    "tldr/pages/osx",
    "tldr/pages/linux",
]

# Whitelist: doar tool-uri folosite frecvent de developeri
ALLOWED_TOOLS = {
    # git & version control
    "git", "gh", "glab", "gitlint", "git-lfs",
    # docker & containers
    "docker", "docker-compose", "podman", "kubectl", "helm", "k9s",
    # package managers & build
    "npm", "npx", "yarn", "pnpm", "bun", "node",
    "pip", "pip3", "python", "python3", "uv", "poetry", "conda",
    "cargo", "rustup", "go", "gradle", "mvn", "make", "cmake",
    "brew", "apt", "apt-get", "yum", "dnf", "pacman",
    "dotnet", "nuget",
    # cloud & infrastructure
    "aws", "az", "gcloud", "terraform", "pulumi",
    # filesystem & system
    "ls", "ll", "la", "cd", "mkdir", "rm", "cp", "mv", "touch",
    "find", "grep", "rg", "fd", "awk", "sed", "cut", "sort", "uniq",
    "cat", "bat", "less", "more", "head", "tail", "wc", "tee",
    "chmod", "chown", "chgrp", "ln", "stat", "file", "du", "df",
    "tar", "zip", "unzip", "gzip", "gunzip", "bzip2", "xz",
    "rsync", "scp", "sftp",
    # network
    "curl", "wget", "ssh", "ping", "nc", "nmap", "netstat", "ss",
    "lsof", "dig", "nslookup", "host", "traceroute", "ifconfig", "ip",
    "openssl", "http",
    # process & system
    "ps", "top", "htop", "kill", "pkill", "killall", "nice", "nohup",
    "systemctl", "service", "journalctl", "cron", "crontab",
    "env", "export", "source", "echo", "printf", "read",
    "which", "whereis", "type", "man", "tldr", "help",
    "history", "alias", "unalias",
    # editors
    "vim", "nvim", "vi", "nano", "code", "emacs",
    # databases
    "psql", "mysql", "mysqldump", "redis-cli", "mongo", "mongosh",
    "sqlite3",
    # tools
    "jq", "yq", "fzf", "tmux", "screen", "watch", "xargs",
    "base64", "md5", "sha256sum", "shasum",
    "date", "cal", "bc",
    "ffmpeg", "convert", "identify",
    "sudo",
}

# Regex pentru a detecta placeholder-e tldr: {{fisier}}, {{ip}}, etc.
PLACEHOLDER_RE = re.compile(r'\{\{.*?\}\}')


def clean_command(cmd: str) -> str | None:
    """
    Curata o comanda extrasa din tldr.
    Returneaza None daca comanda nu e utila pentru training.
    """
    cmd = cmd.strip()

    # Elimina comenzile care incep cu caractere speciale
    if cmd.startswith(('#', '-', '>', '|', '!')):
        return None

    # Inlocuieste placeholder-ele cu valori realiste
    replacements = {
        r'\{\{file(name)?\}\}': 'file.txt',
        r'\{\{source_?file\}\}': 'src.txt',
        r'\{\{target_?file\}\}': 'output.txt',
        r'\{\{directory\}\}': 'mydir',
        r'\{\{path(/to/.*?)?\}\}': '/path/to/file',
        r'\{\{source_?dir(ectory)?\}\}': 'src/',
        r'\{\{target_?dir(ectory)?\}\}': 'dest/',
        r'\{\{image\}\}': 'ubuntu:latest',
        r'\{\{container\}\}': 'mycontainer',
        r'\{\{port\}\}': '8080',
        r'\{\{host(name)?\}\}': 'example.com',
        r'\{\{user(name)?\}\}': 'myuser',
        r'\{\{password\}\}': 'mypassword',
        r'\{\{branch\}\}': 'main',
        r'\{\{remote\}\}': 'origin',
        r'\{\{tag\}\}': 'v1.0.0',
        r'\{\{commit\}\}': 'abc1234',
        r'\{\{message\}\}': '"fix bug"',
        r'\{\{package\}\}': 'mypackage',
        r'\{\{version\}\}': '1.0.0',
        r'\{\{url\}\}': 'https://example.com',
        r'\{\{ip(_address)?\}\}': '192.168.1.1',
        r'\{\{pid\}\}': '1234',
        r'\{\{signal\}\}': 'SIGTERM',
        r'\{\{pattern\}\}': '"search_term"',
        r'\{\{regex\}\}': '"pattern"',
        r'\{\{name\}\}': 'myproject',
        r'\{\{key\}\}': 'mykey',
        r'\{\{value\}\}': 'myvalue',
        r'\{\{namespace\}\}': 'default',
        r'\{\{pod\}\}': 'mypod',
        r'\{\{deployment\}\}': 'myapp',
        r'\{\{service\}\}': 'myservice',
        r'\{\{context\}\}': 'production',
        r'\{\{cluster\}\}': 'mycluster',
        r'\{\{number\}\}': '10',
        r'\{\{count\}\}': '5',
        r'\{\{size\}\}': '100M',
        r'\{\{seconds\}\}': '30',
        r'\{\{minutes\}\}': '5',
        r'\{\{depth\}\}': '3',
        r'\{\{level\}\}': '2',
        r'\{\{mode\}\}': '755',
        r'\{\{permissions?\}\}': '644',
        r'\{\{owner\}\}': 'root',
        r'\{\{group\}\}': 'staff',
        r'\{\{shell\}\}': '/bin/zsh',
        r'\{\{command\}\}': 'ls -la',
        r'\{\{script\}\}': 'script.sh',
        r'\{\{program\}\}': 'myapp',
        r'\{\{args?\}\}': '--verbose',
        r'\{\{options?\}\}': '--force',
        r'\{\{flags?\}\}': '-v',
        r'\{\{output\}\}': 'output.txt',
        r'\{\{input\}\}': 'input.txt',
        r'\{\{format\}\}': 'json',
        r'\{\{type\}\}': 'file',
        r'\{\{extension\}\}': 'txt',
        r'\{\{prefix\}\}': 'app',
        r'\{\{suffix\}\}': '_backup',
        r'\{\{repo(sitory)?\}\}': 'myrepo',
        r'\{\{token\}\}': 'mytoken',
        r'\{\{region\}\}': 'us-east-1',
        r'\{\{bucket\}\}': 'mybucket',
        r'\{\{profile\}\}': 'default',
        r'\{\{role\}\}': 'admin',
        r'\{\{resource\}\}': 'pods',
        r'\{\{label\}\}': 'app=myapp',
        r'\{\{selector\}\}': 'app=frontend',
        r'\{\{replicas?\}\}': '3',
        r'\{\{network\}\}': 'mynetwork',
        r'\{\{volume\}\}': 'myvolume',
        r'\{\{mount\}\}': '/data',
        r'\{\{env(ironment)?\}\}': 'production',
        r'\{\{variable\}\}': 'MY_VAR',
        r'\{\{database\}\}': 'mydb',
        r'\{\{table\}\}': 'users',
        r'\{\{query\}\}': 'SELECT * FROM users',
        r'\{\{server\}\}': 'db.example.com',
        r'\{\{interface\}\}': 'eth0',
        r'\{\{device\}\}': '/dev/sda',
        r'\{\{partition\}\}': '/dev/sda1',
        r'\{\{filesystem\}\}': 'ext4',
        r'\{\{mountpoint\}\}': '/mnt',
        r'\{\{source\}\}': 'src',
        r'\{\{destination\}\}': 'dest',
        r'\{\{origin\}\}': 'origin',
        r'\{\{upstream\}\}': 'upstream',
    }

    for pattern, replacement in replacements.items():
        cmd = re.sub(pattern, replacement, cmd, flags=re.IGNORECASE)

    # Daca mai sunt placeholder-e necunoscute, inlocuieste cu "value"
    cmd = PLACEHOLDER_RE.sub('value', cmd)

    # Curata spatii multiple
    cmd = re.sub(r'\s+', ' ', cmd).strip()

    # Filtreaza comenzi prea scurte (sub 3 chars) sau prea lungi (peste 80)
    if len(cmd) < 4 or len(cmd) > 80:
        return None

    # Filtreaza comenzi care contin lucruri ciudate
    if any(c in cmd for c in ['\\n', '\\t', '\x00', '${', '$(', '`']):
        return None

    # Nu vrem comenzi care incep cu sudo (adauga complexitate)
    # De fapt, le pastram - sudo e comun
    # if cmd.startswith('sudo '):
    #     cmd = cmd[5:].strip()

    # Trebuie sa inceapa cu un tool din whitelist
    words = cmd.split()
    if not words:
        return None
    first_word = words[0]

    # Daca incepe cu sudo, verificam al doilea cuvant
    if first_word == 'sudo':
        actual_tool = words[1] if len(words) > 1 else ''
    else:
        actual_tool = first_word

    if actual_tool not in ALLOWED_TOOLS:
        return None

    # Eliminate tldr from training (useless meta-command)
    if actual_tool == 'tldr':
        return None

    # Fara pipe-uri — prea complexe pentru autocomplete simplu
    if '|' in cmd:
        return None

    # Fara redirectari
    if '>' in cmd or '<' in cmd:
        return None

    # Fara substitutii de comenzi
    if '$(' in cmd or '`' in cmd:
        return None

    # Max 1 placeholder "value" — mai mult = calitate slaba
    if cmd.count('value') > 1:
        return None

    # Fara /path/to/file ca argument (prea generic)
    if cmd.count('/path/to/file') > 1:
        return None

    # Comanda nu trebuie sa contina caractere SQL sau cod
    bad_patterns = ['SELECT', 'FROM', 'WHERE', 'INSERT', 'UPDATE', 'DELETE',
                    'CREATE', 'DROP', 'ALTER', 'INDEX',
                    'function(', 'return ', 'import ', 'require(']
    for pat in bad_patterns:
        if pat in cmd:
            return None

    return cmd


def extract_commands_from_tldr(filepath: Path) -> list[str]:
    """Extrage comenzile din exemple dintr-un fisier tldr markdown."""
    commands = []
    try:
        text = filepath.read_text(encoding='utf-8')
    except Exception:
        return []

    # Ignora fisiere Windows
    tool_name = filepath.stem.lower()
    windows_tools = {"cmd", "powershell", "wsl", "choco", "scoop", "winget", "reg", "regedit"}
    if tool_name in windows_tools:
        return []

    # Extrage liniile care incep cu ` (exemple de comenzi in tldr)
    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('`') and line.endswith('`'):
            cmd_raw = line[1:-1].strip()
            cmd = clean_command(cmd_raw)
            if cmd:
                commands.append(cmd)

    return commands


def get_prefix_positions(cmd: str) -> list[int]:
    """
    Returneaza pozitiile de prefix de folosit pentru training.
    Strategie: word boundaries + cateva pozitii intermediare.
    Minim 2 caractere prefix, maxim len(cmd)-1.
    """
    positions = set()
    words = cmd.split()

    # 1. Pozitii la word boundaries (dupa fiecare cuvant)
    pos = 0
    for i, word in enumerate(words[:-1]):  # nu includem ultima pozitie (comanda completa)
        pos += len(word) + 1  # +1 pentru spatiu
        if 2 <= pos < len(cmd):
            positions.add(pos)

    # 2. Prime 1-5 caractere (invatam de la primele litere)
    for i in range(2, min(6, len(cmd))):
        positions.add(i)

    # 3. Inceputul fiecarui cuvant (primele 1-3 litere din fiecare word segment)
    pos = 0
    for word in words:
        for offset in [1, 2, 3]:
            p = pos + offset
            if 2 <= p < len(cmd):
                positions.add(p)
        pos += len(word) + 1

    # Filtreaza pozitii invalide
    valid = sorted(p for p in positions if 2 <= p < len(cmd))
    return valid


def make_pairs(cmd: str) -> list[dict]:
    """Genereaza perechile de training pentru o comanda."""
    pairs = []
    positions = get_prefix_positions(cmd)

    for pos in positions:
        prefix = cmd[:pos]
        # Skip daca prefixul se termina in spatiu (nenatural)
        # De fapt il pastram - "git " e o pozitie naturala
        pairs.append({
            "messages": [
                {"role": "system",    "content": SYSTEM_PROMPT},
                {"role": "user",      "content": prefix},
                {"role": "assistant", "content": cmd},
            ]
        })

    return pairs


def main():
    print("Extragere comenzi din tldr-pages...")

    all_commands = []
    stats = {}

    for dir_path in TLDR_DIRS:
        path = Path(dir_path)
        if not path.exists():
            print(f"  SKIP (nu exista): {dir_path}")
            continue

        files = list(path.glob("*.md"))
        cmds_in_dir = []
        for f in files:
            cmds = extract_commands_from_tldr(f)
            cmds_in_dir.extend(cmds)

        stats[dir_path] = len(cmds_in_dir)
        all_commands.extend(cmds_in_dir)
        print(f"  {dir_path}: {len(cmds_in_dir)} comenzi din {len(files)} fisiere")

    # Deduplicare
    all_commands = list(dict.fromkeys(all_commands))  # pastreaza ordinea, elimina duplicate
    print(f"\nTotal comenzi unice: {len(all_commands)}")

    # Genereaza perechile de training
    all_pairs = []
    for cmd in all_commands:
        all_pairs.extend(make_pairs(cmd))

    print(f"Total perechi de training: {len(all_pairs)}")

    # Shuffle
    random.seed(42)
    random.shuffle(all_pairs)

    # Split 90/10
    split = int(len(all_pairs) * 0.9)
    train = all_pairs[:split]
    eval_ = all_pairs[split:]

    # Salveaza
    with open("dataset_train_v2.jsonl", "w") as f:
        for item in train:
            f.write(json.dumps(item) + "\n")

    with open("dataset_eval_v2.jsonl", "w") as f:
        for item in eval_:
            f.write(json.dumps(item) + "\n")

    print(f"\nSalvat: {len(train)} train + {len(eval_)} eval")

    # Preview - 20 exemple random pentru verificare
    print("\n" + "="*60)
    print("PREVIEW — 20 exemple random:")
    print("="*60)
    samples = random.sample(train, min(20, len(train)))
    for s in samples:
        prefix = s['messages'][1]['content']
        full   = s['messages'][2]['content']
        print(f"  '{prefix}'")
        print(f"  → '{full}'")
        print()


if __name__ == "__main__":
    main()
