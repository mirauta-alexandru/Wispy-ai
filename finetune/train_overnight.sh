#!/bin/bash
# Antrenament secvential peste noapte pe M4 Pro
# Ruleaza dintr-un terminal si lasa laptopul.
#
# Variante:
#   bash train_overnight.sh safe    → 0.5B + 0.8B (~6-8h, sigur)
#   bash train_overnight.sh full    → 0.8B + 2B    (~9-14h, tight)
#   bash train_overnight.sh all     → toate 3      (~11-18h, risky)

set -e  # opreste la orice eroare

VARIANT=${1:-safe}
START=$(date)

log() {
    echo ""
    echo "========================================"
    echo "  $1"
    echo "  $(date)"
    echo "========================================"
}

cd "$(dirname "$0")"
source venv/bin/activate

case "$VARIANT" in
  safe)
    log "START: qwen25 (0.5B Coder)"
    python train_m4.py qwen25
    log "DONE: qwen25 | START: qwen35_08 (0.8B)"
    python train_m4.py qwen35_08
    log "GATA! Ambele modele antrenate."
    ;;
  full)
    log "START: qwen35_08 (0.8B)"
    python train_m4.py qwen35_08
    log "DONE: qwen35_08 | START: qwen35_2b (2B)"
    python train_m4.py qwen35_2b
    log "GATA! Ambele modele antrenate."
    ;;
  all)
    log "START: qwen25 (0.5B Coder)"
    python train_m4.py qwen25
    log "DONE: qwen25 | START: qwen35_08 (0.8B)"
    python train_m4.py qwen35_08
    log "DONE: qwen35_08 | START: qwen35_2b (2B)"
    python train_m4.py qwen35_2b
    log "GATA! Toate 3 modele antrenate."
    ;;
  *)
    echo "Folosire: bash train_overnight.sh [safe|full|all]"
    echo "  safe → 0.5B + 0.8B  (~6-8h)"
    echo "  full → 0.8B + 2B    (~9-14h)"
    echo "  all  → toate 3      (~11-18h)"
    exit 1
    ;;
esac

echo ""
echo "Inceput: $START"
echo "Terminat: $(date)"
