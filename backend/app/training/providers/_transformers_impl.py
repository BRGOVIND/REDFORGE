"""Real Hugging Face Transformers LoRA/QLoRA/SFT recipe (GPU-only).

The concrete counterpart to :mod:`_unsloth_impl`, isolated in its own module so the
heavy imports (``torch``/``transformers``/``peft``/``trl``) happen only when a GPU +
the ML stack are present. Never imported in CI (no GPU). :class:`TransformersProvider`
delegates here; this file translates HF Trainer callbacks into :class:`ProgressEvent`s.

Why this exists as a sibling to Unsloth: Unsloth is the fast path but does not support
every model/architecture. When Unsloth is absent (or can't run a given base model) but
the stock ``transformers + peft + trl`` stack is installed on a CUDA GPU, RedForge
falls back to this provider so training still runs.

CONCURRENCY CONTRACT (RedForge is single-process asyncio — Constitution §8): identical
to :mod:`_unsloth_impl`. Every blocking call here — the multi-GB ``from_pretrained``
download+load, PEFT wiring, dataset tokenization, trainer construction,
``trainer.train()``, and ``save_model`` — runs on a **background thread**. The async
generator only drains a queue and ``await``s, so the event loop is NEVER blocked and
progress/health endpoints stay responsive while a model downloads or trains. Each phase
pushes a human-readable ``ProgressEvent`` so the user always sees what is happening.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from app.training.providers.base import ProgressEvent, TrainingConfig


async def run_transformers(config: TrainingConfig, cancel) -> AsyncIterator[ProgressEvent]:  # pragma: no cover
    """Execute a real LoRA/QLoRA/SFT run via stock Transformers + PEFT + TRL. Requires
    torch/transformers/peft/trl + a CUDA GPU (guarded by
    ``TransformersProvider.is_available`` before this runs).

    All heavy work happens on a worker thread; this coroutine only forwards the events
    the thread produces, so it never stalls the single-process event loop."""
    import queue
    import threading

    events: "queue.Queue[ProgressEvent]" = queue.Queue()
    done = threading.Event()
    # Capture the worker thread's real exception so it is SURFACED, not swallowed
    # (the true error — OOM, model-download failure — must reach the user, not be
    # replaced by a downstream error).
    holder: dict = {"error": None}

    def _phase(message: str) -> None:
        events.put(ProgressEvent(status="running", message=message))

    def _work() -> None:
        try:
            # Heavy imports happen on the thread too — importing torch/transformers is
            # itself slow and must not block the loop.
            import torch  # type: ignore
            from transformers import (  # type: ignore
                AutoModelForCausalLM, AutoTokenizer, TrainingArguments, TrainerCallback,
            )
            from peft import LoraConfig, get_peft_model  # type: ignore
            from trl import SFTTrainer  # type: ignore
            from datasets import Dataset  # type: ignore

            load_in_4bit = config.method == "qlora"

            _phase(f"Downloading base model & tokenizer ({config.base_model})…")
            tokenizer = AutoTokenizer.from_pretrained(config.base_model, use_fast=True)
            if tokenizer.pad_token is None:
                # Causal LMs frequently ship without a pad token; reuse EOS so batching
                # and the trainer's collator work without mutating the vocabulary.
                tokenizer.pad_token = tokenizer.eos_token

            model_kwargs: dict = {}
            if load_in_4bit:
                from transformers import BitsAndBytesConfig  # type: ignore
                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True, bnb_4bit_quant_type="nf4",
                    bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.bfloat16,
                )
                model_kwargs["device_map"] = "auto"
            else:
                model_kwargs["torch_dtype"] = torch.bfloat16
                model_kwargs["device_map"] = "auto"

            model = AutoModelForCausalLM.from_pretrained(config.base_model, **model_kwargs)

            if load_in_4bit:
                from peft import prepare_model_for_kbit_training  # type: ignore
                model = prepare_model_for_kbit_training(model)

            _phase("Attaching LoRA adapters…")
            lora = LoraConfig(
                r=config.rank, lora_alpha=config.alpha, lora_dropout=config.dropout,
                bias="none", task_type="CAUSAL_LM",
            )
            model = get_peft_model(model, lora)

            # Records → a text dataset (expects {"text": ...} or instruction fields).
            def _to_text(rec):
                if isinstance(rec, dict):
                    return rec.get("text") or "\n".join(str(v) for v in rec.values())
                return str(rec)

            _phase("Preparing dataset…")
            ds = Dataset.from_dict({"text": [_to_text(r) for r in config.dataset_records]})

            last = {"step": 0, "loss": None, "val_loss": None, "epoch": 0.0, "total_steps": 0}

            class _Bridge(TrainerCallback):
                def on_log(self, args, state, control, logs=None, **kw):
                    if cancel():
                        control.should_training_stop = True
                    logs = logs or {}
                    last.update(step=state.global_step, total_steps=state.max_steps,
                                epoch=state.epoch or 0.0,
                                loss=logs.get("loss", last["loss"]),
                                val_loss=logs.get("eval_loss", last["val_loss"]))
                    events.put(ProgressEvent(
                        status="running", step=state.global_step,
                        total_steps=state.max_steps, epoch=state.epoch or 0.0,
                        total_epochs=config.epochs, loss=logs.get("loss"),
                        val_loss=logs.get("eval_loss"), learning_rate=logs.get("learning_rate"),
                    ))

            _phase("Creating trainer…")
            args = TrainingArguments(
                per_device_train_batch_size=config.batch_size,
                gradient_accumulation_steps=config.gradient_accumulation,
                warmup_steps=config.warmup_steps, num_train_epochs=config.epochs,
                learning_rate=config.learning_rate, lr_scheduler_type=config.scheduler,
                optim=config.optimizer, seed=config.seed,
                output_dir=config.output_dir or "outputs", logging_steps=1,
                bf16=True,
                # We persist the LoRA adapter ourselves (save_pretrained); disable the
                # Trainer's own checkpoint save so it never pickles training_args.bin.
                save_strategy="no", report_to="none",
            )
            trainer = SFTTrainer(
                model=model, tokenizer=tokenizer, train_dataset=ds,
                dataset_text_field="text", max_seq_length=config.max_seq_length,
                args=args, callbacks=[_Bridge()],
            )

            _phase("Compiling kernels & training…")
            trainer.train()

            # Only persist a completed run (a cancel stops training early).
            if not cancel():
                out_dir = config.output_dir or "outputs"
                _phase("Saving LoRA adapter…")
                # Save the PEFT adapter directly (adapter_config.json +
                # adapter_model.safetensors) rather than trainer.save_model(), which
                # also pickles training_args.bin — avoided here for the same reason as
                # the Unsloth recipe and because the adapter is the real artifact.
                import os as _os
                _os.makedirs(out_dir, exist_ok=True)
                model.save_pretrained(out_dir)
                try:
                    tokenizer.save_pretrained(out_dir)
                except Exception:  # noqa: BLE001 - tokenizer save is best-effort
                    pass
                events.put(ProgressEvent(
                    status="running", step=last["step"], total_steps=last["total_steps"],
                    epoch=last["epoch"], total_epochs=config.epochs, loss=last["loss"],
                    val_loss=last["val_loss"], message="Saved checkpoint (LoRA adapter)",
                    checkpoint={"step": last["step"], "epoch": last["epoch"],
                                "loss": last["loss"], "val_loss": last["val_loss"],
                                "path": out_dir, "is_best": 1},
                ))
            holder["final"] = dict(last)
        except BaseException as exc:  # noqa: BLE001 - surface the real training error
            holder["error"] = exc
        finally:
            done.set()

    threading.Thread(target=_work, daemon=True).start()

    # Drain the worker's events without ever blocking the loop.
    while not done.is_set() or not events.empty():
        try:
            yield events.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.1)

    if holder["error"] is not None:
        import traceback
        tb = "".join(traceback.format_exception(holder["error"]))
        yield ProgressEvent(status="failed",
                            message=f"training error: {holder['error']}\n{tb[-800:]}")
        return
    if cancel():
        yield ProgressEvent(status="cancelled", message="cancelled by user")
        return
    fin = holder.get("final") or {}
    yield ProgressEvent(status="completed", message="training complete",
                        step=fin.get("step", 0), total_steps=fin.get("total_steps", 0),
                        epoch=fin.get("epoch", 0.0), total_epochs=config.epochs,
                        loss=fin.get("loss"), val_loss=fin.get("val_loss"))
