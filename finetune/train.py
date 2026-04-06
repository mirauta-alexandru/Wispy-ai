"""
Fine-tunes Qwen3.5-0.8B on shell command completions using LoRA.
Runs on Apple Silicon (MPS).

Usage:
  python train.py
"""

import json
import torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer, SFTConfig

MODEL_ID   = "Qwen/Qwen3.5-0.8B"
OUTPUT_DIR = "./wispy-finetuned"
DEVICE     = "mps" if torch.backends.mps.is_available() else "cpu"
MAX_LENGTH = 128

print(f"Device: {DEVICE}")
print(f"Model:  {MODEL_ID}")


# ── Dataset ───────────────────────────────────────────────────────────────────

def load_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]

train_data = load_jsonl("dataset_train.jsonl")
eval_data  = load_jsonl("dataset_eval.jsonl")
print(f"Train: {len(train_data)} | Eval: {len(eval_data)}")


# ── Tokenizer ─────────────────────────────────────────────────────────────────

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
tokenizer.pad_token = tokenizer.eos_token

def format_example(example):
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
        enable_thinking=False,   # Qwen3 thinking mode off — nu avem nevoie pentru autocomplete
    )
    return {"text": text}

train_dataset = Dataset.from_list(train_data).map(format_example)
eval_dataset  = Dataset.from_list(eval_data).map(format_example)


# ── Model + LoRA ──────────────────────────────────────────────────────────────

print("Loading model...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    dtype=torch.bfloat16,
    trust_remote_code=True,
)
model = model.to(DEVICE)

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


# ── Training ──────────────────────────────────────────────────────────────────

training_args = SFTConfig(
    output_dir=OUTPUT_DIR,
    num_train_epochs=3,
    per_device_train_batch_size=8,
    per_device_eval_batch_size=8,
    gradient_accumulation_steps=2,
    warmup_steps=50,
    learning_rate=2e-4,
    fp16=False,
    bf16=False,
    logging_steps=10,
    eval_strategy="steps",
    eval_steps=100,
    save_steps=200,
    save_total_limit=2,
    load_best_model_at_end=True,
    report_to="none",
    dataloader_pin_memory=False,
    dataset_text_field="text",
    max_length=MAX_LENGTH,
)

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    processing_class=tokenizer,
)

print("Starting training...")
trainer.train()

print(f"\nSaving to {OUTPUT_DIR}...")
trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)
print("Done! Run: bash convert_to_gguf.sh")
