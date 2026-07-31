"""Standalone training worker — executed BY THE MANAGED RUNTIME INTERPRETER.

    <runtime>/venv/bin/python worker.py <config.json>

This file is deliberately **self-contained**: it must not import anything from
``app.*``. The managed virtual environment contains only the training stack, not
RedForge, so any RedForge import here would crash the subprocess. Treat this as a
separate program that happens to live in the repo.

Protocol — one JSON object per line on stdout, each prefixed so ordinary library
chatter (which is copious) can be filtered out:

    @@RF@@{"status": "running", "step": 3, "total": 40, "loss": 1.83, ...}

Statuses: ``starting`` · ``running`` · ``checkpoint`` · ``completed`` · ``failed``.
The parent (``providers/managed.py``) turns these into ProgressEvents.

Exit code is 0 on success, 1 on failure; the final line is always terminal.
"""
from __future__ import annotations

import json
import os
import sys
import traceback

PREFIX = "@@RF@@"


def emit(**payload) -> None:
    """One protocol line. Flushed immediately so the parent streams in real time."""
    try:
        sys.stdout.write(PREFIX + json.dumps(payload, default=str) + "\n")
        sys.stdout.flush()
    except Exception:
        pass


def _records_to_texts(records: list, max_seq_length: int) -> list[str]:
    """Accept the shapes RedForge datasets actually produce."""
    texts: list[str] = []
    for record in records:
        if isinstance(record, str):
            texts.append(record)
            continue
        if not isinstance(record, dict):
            continue
        if record.get("text"):
            texts.append(str(record["text"]))
            continue
        prompt = record.get("prompt") or record.get("instruction") or record.get("input") or ""
        completion = record.get("completion") or record.get("output") or record.get("response") or ""
        if prompt or completion:
            texts.append(f"### Instruction:\n{prompt}\n\n### Response:\n{completion}")
    return [t for t in texts if t.strip()]


def main() -> int:
    if len(sys.argv) < 2:
        emit(status="failed", message="worker requires a config file path")
        return 1
    try:
        with open(sys.argv[1], "r", encoding="utf-8") as handle:
            cfg = json.load(handle)
    except Exception as exc:
        emit(status="failed", message=f"could not read config: {exc}")
        return 1

    # Keep *generated code* inside the managed runtime, never the CWD or a watched
    # source tree (this was a real defect once — uvicorn's reloader watched the
    # compile cache and restarted mid-training).
    #
    # Deliberately NOT redirected: HF_HOME. Model weights must resolve through the
    # user's normal Hugging Face cache, which is where the Model Hub puts them.
    # Pointing it into the runtime directory would hide every already-downloaded
    # model and silently re-download gigabytes.
    cache_dir = cfg.get("cache_dir")
    if cache_dir:
        os.environ.setdefault("UNSLOTH_COMPILE_LOCATION", os.path.join(cache_dir, "unsloth_compiled_cache"))
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

    try:
        emit(status="starting", message="loading training engine (torch + unsloth)…")
        from unsloth import FastLanguageModel  # noqa: E402
        import torch  # noqa: E402
        from datasets import Dataset  # noqa: E402
        from transformers import TrainingArguments, TrainerCallback  # noqa: E402
        from trl import SFTTrainer  # noqa: E402
    except Exception as exc:
        emit(status="failed", message=f"training engine unavailable: {exc}",
             detail=traceback.format_exc()[-1500:])
        return 1

    try:
        base_model = cfg["base_model"]
        method = (cfg.get("method") or "lora").lower()
        load_in_4bit = method == "qlora"
        max_seq_length = int(cfg.get("max_seq_length") or 2048)
        output_dir = cfg["output_dir"]
        os.makedirs(output_dir, exist_ok=True)

        emit(status="starting", message=f"loading {base_model} ({method}, 4bit={load_in_4bit})…")
        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=base_model,
            max_seq_length=max_seq_length,
            dtype=None,
            load_in_4bit=load_in_4bit,
        )

        emit(status="starting", message="attaching LoRA adapters…")
        model = FastLanguageModel.get_peft_model(
            model,
            r=int(cfg.get("rank") or 16),
            lora_alpha=int(cfg.get("alpha") or 16),
            lora_dropout=float(cfg.get("dropout") or 0.0),
            target_modules=cfg.get("target_modules") or [
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ],
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=int(cfg.get("seed") or 3407),
        )

        texts = _records_to_texts(cfg.get("dataset_records") or [], max_seq_length)
        if not texts:
            emit(status="failed", message="dataset produced no usable training text")
            return 1
        emit(status="starting", message=f"prepared {len(texts)} training examples")
        dataset = Dataset.from_dict({"text": texts})

        total_holder = {"total": 0}
        last = {"step": 0, "loss": None, "epoch": 0.0}

        class Reporter(TrainerCallback):
            """Bridges HF Trainer callbacks onto the line protocol."""

            def on_train_begin(self, args, state, control, **kwargs):
                total_holder["total"] = int(state.max_steps or 0)
                emit(status="running", message="training started",
                     step=0, total=total_holder["total"])

            def on_log(self, args, state, control, logs=None, **kwargs):
                logs = logs or {}
                if "loss" not in logs:
                    return
                last["step"] = int(state.global_step or 0)
                last["loss"] = float(logs["loss"])
                last["epoch"] = float(state.epoch or 0.0)
                emit(status="running", step=last["step"], total=total_holder["total"],
                     loss=last["loss"], epoch=last["epoch"],
                     learning_rate=logs.get("learning_rate"))

        args = TrainingArguments(
            per_device_train_batch_size=int(cfg.get("batch_size") or 2),
            gradient_accumulation_steps=int(cfg.get("gradient_accumulation") or 1),
            warmup_steps=int(cfg.get("warmup_steps") or 0),
            num_train_epochs=float(cfg.get("epochs") or 1),
            learning_rate=float(cfg.get("learning_rate") or 2e-4),
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=1,
            optim=cfg.get("optimizer") or "adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type=cfg.get("scheduler") or "linear",
            seed=int(cfg.get("seed") or 3407),
            output_dir=os.path.join(output_dir, "_trainer"),
            # Transformers' end-of-epoch save cannot pickle the Unsloth-patched
            # config; we save the adapter explicitly below instead.
            save_strategy="no",
            report_to="none",
        )

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=dataset,
            dataset_text_field="text",
            max_seq_length=max_seq_length,
            args=args,
            callbacks=[Reporter()],
        )

        trainer.train()

        emit(status="running", message="saving adapter…",
             step=last["step"], total=total_holder["total"])
        model.save_pretrained(output_dir)
        try:
            tokenizer.save_pretrained(output_dir)
        except Exception:
            pass

        emit(status="checkpoint", path=output_dir, step=last["step"],
             total=total_holder["total"], epoch=last["epoch"], loss=last["loss"], is_best=1)
        emit(status="completed", message="training complete", step=last["step"],
             total=total_holder["total"], loss=last["loss"], epoch=last["epoch"],
             output_dir=output_dir)
        return 0
    except Exception as exc:
        emit(status="failed", message=f"training error: {exc}",
             detail=traceback.format_exc()[-1800:])
        return 1


if __name__ == "__main__":
    sys.exit(main())
