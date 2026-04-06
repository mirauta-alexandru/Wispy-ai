"""
Ultra-Fast Training Script for M4 Pro (MPS)
Model: Qwen 3.5 0.8B
Optimized for Speed (< 6 hours)
"""

import sys
import json
import torch
import os
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer, SFTConfig

# Optimizare specifica pentru MPS
os.environ["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] = "0.0"

CONFIGS = {
    "qwen35_08": {
        "model_id":    "Qwen/Qwen3.5-0.8B",
        "output_dir":  "./wispy-qwen35-08-finetuned",
        "thinking":    False,
        "epochs":      3,         # Redus la 3 pentru viteza (si suficient pentru v3)
        "batch_size":  64,        # Dublat la 64 pentru a "rupe" GPU-ul
        "lr":          2e-4,
        "max_length":  128,
    },
}

cfg = CONFIGS["qwen35_08"]
MODEL_ID   = cfg["model_id"]
OUTPUT_DIR = cfg["output_dir"]
DEVICE     = "mps" if torch.backends.mps.is_available() else "cpu"

print(f"Model:  {MODEL_ID}")
print(f"Device: {DEVICE}")

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
            example["messages"],
            **kwargs,
            enable_thinking=cfg["thinking"],
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

# DEZACTIVAM Gradient Checkpointing pentru viteza (avem destul RAM)
model.gradient_checkpointing_disable()

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
    gradient_accumulation_steps=1,
    warmup_steps=50,
    learning_rate=cfg["lr"],
    fp16=False,
    bf16=False,
    logging_steps=50,           # Mai putine log-uri = mai multa viteza
    eval_strategy="steps",
    eval_steps=100,
    save_steps=200,
    save_total_limit=2,
    load_best_model_at_end=True,
    report_to="none",
    
    dataloader_num_workers=2,   # 2 workers sunt suficienti si mai stabili pe macOS
    dataloader_pin_memory=False,
    gradient_checkpointing=False, # Dezactivat pentru viteză
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

print(f"\nStarting ULTRA-FAST training...")
trainer.train()

print(f"\nSaving to {OUTPUT_DIR}...")
trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print(f"Done! Model saved to {OUTPUT_DIR}")
