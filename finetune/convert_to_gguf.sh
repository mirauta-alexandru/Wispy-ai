#!/usr/bin/env bash
# Merges LoRA weights into the base model and converts to GGUF for llama.cpp
set -e

FINETUNED_DIR="./wispy-finetuned"
MERGED_DIR="./wispy-merged"
GGUF_FILE="./wispy-shell-0.5b-q4.gguf"
LLAMA_CPP_DIR="$HOME/.wispy-ai/bin/build/llama.cpp"

echo "=> Merging LoRA into base model..."
python3 - <<'EOF'
from peft import AutoPeftModelForCausalLM
from transformers import AutoTokenizer
import torch

model = AutoPeftModelForCausalLM.from_pretrained(
    "./wispy-finetuned",
    torch_dtype=torch.float32,
    trust_remote_code=True,
)
model = model.merge_and_unload()
model.save_pretrained("./wispy-merged")

tokenizer = AutoTokenizer.from_pretrained("./wispy-finetuned", trust_remote_code=True)
tokenizer.save_pretrained("./wispy-merged")
print("Merge complete.")
EOF

echo "=> Converting to GGUF..."
python3 "$LLAMA_CPP_DIR/convert_hf_to_gguf.py" \
    "$MERGED_DIR" \
    --outfile "$GGUF_FILE" \
    --outtype q8_0

echo "=> Quantizing to Q4_K_M..."
"$LLAMA_CPP_DIR/build/bin/llama-quantize" \
    "$GGUF_FILE" \
    "./wispy-shell-0.5b-q4_k_m.gguf" \
    Q4_K_M

echo ""
echo "Done! File: wispy-shell-0.5b-q4_k_m.gguf"
echo "Upload to HuggingFace and update MODEL_URL in main.rs"
