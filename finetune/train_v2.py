"""
Fine-tuning v2 pe dataset v3 (comenzi complete, fara placeholder-e).

Modele suportate:
  python train_v2.py qwen25    → Qwen/Qwen2.5-Coder-0.5B-Instruct
  python train_v2.py qwen35_08 → Qwen/Qwen3.5-0.8B
  python train_v2.py qwen35_2b → Qwen/Qwen3.5-2B

Strategie training:
  - Output = comanda completa (nu sufix) → fara ambiguitate
  - User trimite prefixul, modelul returneaza comanda completa
  - La inferenta: strip prefix din raspuns = sufixul de afisat
"""

import sys
import json
import torch
from datasets import Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer, SFTConfig

# ── Configuratie modele ────────────────────────────────────────────────────────

CONFIGS = {
    "qwen25": {
        "model_id":    "Qwen/Qwen2.5-Coder-0.5B-Instruct",
        "output_dir":  "./wispy-qwen25-finetuned",
        "thinking":    False,   # Qwen2.5 nu are thinking mode
        "epochs":      5,
        "batch_size":  8,
        "lr":          2e-4,
        "max_length":  128,
    },
    "qwen35_08": {
        "model_id":    "Qwen/Qwen3.5-0.8B",
        "output_dir":  "./wispy-qwen35-08-finetuned",
        "thinking":    False,   # dezactivam thinking pentru autocomplete
        "epochs":      5,
        "batch_size":  8,
        "lr":          2e-4,
        "max_length":  128,
    },
    "qwen35_2b": {
        "model_id":    "Qwen/Qwen3.5-2B",
        "output_dir":  "./wispy-qwen35-2b-finetuned",
        "thinking":    False,
        "epochs":      4,
        "batch_size":  4,       # batch mai mic pentru modelul mare
        "lr":          1e-4,
        "max_length":  128,
    },
}

# ── Selectare model ────────────────────────────────────────────────────────────

if len(sys.argv) < 2 or sys.argv[1] not in CONFIGS:
    print("Folosire: python train_v2.py [qwen25|qwen35_08|qwen35_2b]")
    sys.exit(1)

cfg = CONFIGS[sys.argv[1]]
MODEL_ID   = cfg["model_id"]
OUTPUT_DIR = cfg["output_dir"]
DEVICE     = "mps" if torch.backends.mps.is_available() else "cpu"

print(f"Model:  {MODEL_ID}")
print(f"Output: {OUTPUT_DIR}")
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
    # Kwargs pentru apply_chat_template
    kwargs = {
        "tokenize":              False,
        "add_generation_prompt": False,
    }
    # Qwen3.5 suporta enable_thinking, Qwen2.5 nu
    try:
        text = tokenizer.apply_chat_template(
            example["messages"],
            **kwargs,
            enable_thinking=cfg["thinking"],
        )
    except TypeError:
        # Qwen2.5 nu are parametrul enable_thinking
        text = tokenizer.apply_chat_template(
            example["messages"],
            **kwargs,
        )
    return {"text": text}

train_dataset = Dataset.from_list(train_data).map(format_example)
eval_dataset  = Dataset.from_list(eval_data).map(format_example)

# Verificam un exemplu
print("\nExemplu format training:")
print(train_dataset[0]["text"][:300])
print("...")

# ── Model + LoRA ───────────────────────────────────────────────────────────────

print("\nLoading model...")
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

# ── Training ───────────────────────────────────────────────────────────────────

training_args = SFTConfig(
    output_dir=OUTPUT_DIR,
    num_train_epochs=cfg["epochs"],
    per_device_train_batch_size=cfg["batch_size"],
    per_device_eval_batch_size=cfg["batch_size"],
    gradient_accumulation_steps=2,
    warmup_steps=50,
    learning_rate=cfg["lr"],
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
print("Next: bash convert_to_gguf.sh <output_dir>")
