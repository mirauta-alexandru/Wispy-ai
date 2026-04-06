"""
Fine-tuning pentru M4 Pro 24GB RAM - optimizat anti-crash.

Modele:
  python train_m4.py qwen25      → Qwen/Qwen2.5-Coder-0.5B-Instruct  (~2-3h)
  python train_m4.py qwen35_08   → Qwen/Qwen3.5-0.8B                 (~3-5h)
  python train_m4.py qwen35_2b   → Qwen/Qwen3.5-2B                   (~6-10h)
"""

import sys
import json
import os
import torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer, SFTConfig

# HIGH_WATERMARK: limita superioara de RAM (70%). LOW trebuie setat explicit,
# altfel PyTorch calculeaza 2×HIGH = 1.4 → invalid → crash.
os.environ["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] = "0.85"
os.environ["PYTORCH_MPS_LOW_WATERMARK_RATIO"] = "0.5"

CONFIGS = {
    "qwen25": {
        "model_id":   "Qwen/Qwen2.5-Coder-0.5B-Instruct",
        "output_dir": "./wispy-qwen25-finetuned",
        "thinking":   False,
        "epochs":     3,
        "batch_size": 8,   # 0.5B ~1GB bfloat16, 24GB are headroom masiv
        "grad_accum": 8,   # effective batch tot 64 (8×8), dar mai putine pasi de acumulare = mai rapid
        "lr":         2e-4,
        "max_length": 256, # comenzile de terminal pot fi verbose (pipe-uri, flags lungi)
    },
    "qwen35_08": {
        "model_id":   "Qwen/Qwen3.5-0.8B",
        "output_dir": "./wispy-qwen35-08-finetuned",
        "thinking":   False,
        "epochs":     3,
        "batch_size": 6,   # 0.8B ~1.6GB, tot confortabil pe 24GB
        "grad_accum": 10,  # effective batch ~60, aproape de 64
        "lr":         2e-4,
        "max_length": 256,
    },
    "qwen35_2b": {
        "model_id":   "Qwen/Qwen3.5-2B",
        "output_dir": "./wispy-qwen35-2b-finetuned",
        "thinking":   False,
        "epochs":     2,
        "batch_size": 4,   # 2B ~4GB, cu grad checkpointing incape bine
        "grad_accum": 16,  # effective batch 64
        "lr":         1e-4,
        "max_length": 256,
    },
}

if len(sys.argv) < 2 or sys.argv[1] not in CONFIGS:
    print("Folosire: python train_m4.py [qwen25|qwen35_08|qwen35_2b]")
    sys.exit(1)

cfg        = CONFIGS[sys.argv[1]]
MODEL_ID   = cfg["model_id"]
OUTPUT_DIR = cfg["output_dir"]
DEVICE     = "mps" if torch.backends.mps.is_available() else "cpu"

print(f"Model:  {MODEL_ID}")
print(f"Output: {OUTPUT_DIR}")
print(f"Device: {DEVICE}")
print(f"Effective batch size: {cfg['batch_size'] * cfg['grad_accum']}")

# ── Dataset ────────────────────────────────────────────────────────────────────

def load_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]

train_data = load_jsonl("dataset_train_v3.jsonl")
eval_data  = load_jsonl("dataset_eval_v3.jsonl")
print(f"Train: {len(train_data)} | Eval: {len(eval_data)}")

# ── Tokenizer ──────────────────────────────────────────────────────────────────

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

def format_example(example):
    kwargs = {"tokenize": False, "add_generation_prompt": False}
    try:
        text = tokenizer.apply_chat_template(
            example["messages"], **kwargs, enable_thinking=cfg["thinking"]
        )
    except TypeError:
        text = tokenizer.apply_chat_template(example["messages"], **kwargs)
    return {"text": text}

train_dataset = Dataset.from_list(train_data).map(format_example)
eval_dataset  = Dataset.from_list(eval_data).map(format_example)

# ── Model + LoRA ───────────────────────────────────────────────────────────────

print("\nLoading model in bfloat16...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    dtype=torch.bfloat16,
    trust_remote_code=True,
)
model = model.to(DEVICE)

# Gradient checkpointing: recompute activatiile in loc sa le tina in RAM
# Viteza -20% dar economisesti 40-60% RAM = esential anti-crash
model.gradient_checkpointing_enable(
    gradient_checkpointing_kwargs={"use_reentrant": False}
)

lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    bias="none",
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# ── Training ───────────────────────────────────────────────────────────────────

training_args = SFTConfig(
    output_dir=OUTPUT_DIR,
    num_train_epochs=cfg["epochs"],
    per_device_train_batch_size=cfg["batch_size"],
    per_device_eval_batch_size=cfg["batch_size"],
    gradient_accumulation_steps=cfg["grad_accum"],
    warmup_steps=50,
    learning_rate=cfg["lr"],
    fp16=False,
    bf16=False,
    logging_steps=50,
    eval_strategy="steps",
    eval_steps=200,
    save_steps=400,
    save_total_limit=2,
    load_best_model_at_end=True,
    report_to="none",
    dataloader_num_workers=0,   # 0 = fara procese extra pe macOS
    dataloader_pin_memory=False,
    gradient_checkpointing=True,
    optim="adamw_torch",
    dataset_text_field="text",
    max_length=cfg["max_length"],
)

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    processing_class=tokenizer,
)

print(f"\nStarting training ({cfg['epochs']} epochs)...")
trainer.train()

print(f"\nSaving to {OUTPUT_DIR}...")
trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"Done! Model saved to {OUTPUT_DIR}")
print("Next: bash convert_to_gguf.sh", OUTPUT_DIR)
