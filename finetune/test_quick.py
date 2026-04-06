"""
Test rapid pentru cele 2 modele noi finetuned.
Ruleaza: python test_quick.py
"""
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

SYSTEM = "You are a zsh terminal autocomplete. Given a partial command, output the complete command on a single line. No explanation, no markdown, no extra text."

PROMPTS = [
    "git push origin ",
    "docker run -it ",
    "npm install --save-dev ",
    "grep -r \"TODO\" ",
    "kubectl get pods -n ",
    "python3 -m venv ",
    "git log --oneline -",
    "ssh -i ~/.ssh/",
    "tar -xzf ",
    "cargo build --rel",
]

MODELS = [
    {
        "name": "qwen25 (0.5B Coder)",
        "base": "Qwen/Qwen2.5-Coder-0.5B-Instruct",
        "adapter": "./wispy-qwen25-finetuned",
        "thinking": False,
    },
    {
        "name": "qwen35-08 (0.8B)",
        "base": "Qwen/Qwen3.5-0.8B",
        "adapter": "./wispy-qwen35-08-finetuned",
        "thinking": False,
    },
]

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"


def run_model(cfg):
    print(f"\n{'='*60}")
    print(f"  Model: {cfg['name']}")
    print(f"{'='*60}")

    tokenizer = AutoTokenizer.from_pretrained(cfg["adapter"], trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        cfg["base"],
        dtype=torch.bfloat16,
        trust_remote_code=True,
    ).to(DEVICE)

    model = PeftModel.from_pretrained(base_model, cfg["adapter"])
    model.set_adapter("default")
    model.eval()

    for prompt in PROMPTS:
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ]
        try:
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=cfg["thinking"],
            )
        except TypeError:
            text = tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )

        inputs = tokenizer(text, return_tensors="pt").to(DEVICE)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=40,
                do_sample=False,
                temperature=None,
                top_p=None,
                pad_token_id=tokenizer.eos_token_id,
            )

        generated = outputs[0][inputs["input_ids"].shape[1]:]
        result = tokenizer.decode(generated, skip_special_tokens=True).strip()

        # Ia doar prima linie
        result = result.split("\n")[0].strip()

        ok = "OK" if result.startswith(prompt.strip()) else "??"
        print(f"  [{ok}] IN:  {prompt!r}")
        print(f"        OUT: {result!r}")
        print()

    del model, base_model
    if DEVICE == "mps":
        torch.mps.empty_cache()


if __name__ == "__main__":
    for cfg in MODELS:
        run_model(cfg)

    print("Done!")
