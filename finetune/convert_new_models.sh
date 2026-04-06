#!/usr/bin/env bash
# Converteste cele 2 modele noi la GGUF Q4_K_M
set -e

CONVERT_SCRIPT="$HOME/.cargo/registry/src/index.crates.io-1949cf8c6b5b557f/llama-cpp-sys-2-0.1.138/llama.cpp/convert_hf_to_gguf.py"
QUANTIZE="$HOME/.ai-autocomplete/bin/build/bin/llama-quantize"

cd "$(dirname "$0")"
source venv/bin/activate

merge_model() {
    local ADAPTER=$1
    local MERGED=$2

    echo "=> Merging LoRA: $ADAPTER -> $MERGED"
    python3 - <<EOF
from peft import AutoPeftModelForCausalLM
from transformers import AutoTokenizer
import torch

model = AutoPeftModelForCausalLM.from_pretrained(
    "$ADAPTER",
    torch_dtype=torch.float32,
    trust_remote_code=True,
)
model = model.merge_and_unload()
model.save_pretrained("$MERGED")

tokenizer = AutoTokenizer.from_pretrained("$ADAPTER", trust_remote_code=True)
tokenizer.save_pretrained("$MERGED")
print("Merge OK.")
EOF
}

convert_model() {
    local MERGED=$1
    local OUT_F16=$2
    local OUT_Q4=$3

    echo "=> Convertire GGUF f16: $MERGED -> $OUT_F16"
    python3 "$CONVERT_SCRIPT" "$MERGED" --outfile "$OUT_F16" --outtype f16

    echo "=> Quantizare Q4_K_M: $OUT_F16 -> $OUT_Q4"
    "$QUANTIZE" "$OUT_F16" "$OUT_Q4" Q4_K_M

    echo "=> Gata: $OUT_Q4"
    ls -lh "$OUT_Q4"
}

echo ""
echo "========================================"
echo "  1/2: qwen25 (0.5B Coder)"
echo "========================================"
merge_model "./wispy-qwen25-finetuned"  "./wispy-qwen25-merged"
convert_model "./wispy-qwen25-merged"   "./wispy-qwen25-f16.gguf"  "./wispy-qwen25-q4_k_m.gguf"

echo ""
echo "========================================"
echo "  2/2: qwen35-08 (0.8B)"
echo "========================================"
merge_model "./wispy-qwen35-08-finetuned"  "./wispy-qwen35-08-merged"
convert_model "./wispy-qwen35-08-merged"   "./wispy-qwen35-08-f16.gguf"  "./wispy-qwen35-08-q4_k_m.gguf"

echo ""
echo "========================================"
echo "  GATA! Fisiere generate:"
echo "========================================"
ls -lh wispy-qwen25-q4_k_m.gguf wispy-qwen35-08-q4_k_m.gguf
