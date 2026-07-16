"""Real Unsloth LoRA/QLoRA recipe (GPU-only).

Isolated in its own module so the heavy imports happen only when a GPU + the ML
stack are present. Never imported in CI (no GPU). This is the concrete training
loop that :class:`UnslothProvider` delegates to; it translates HF Trainer
callbacks into :class:`ProgressEvent`s.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from app.training.providers.base import ProgressEvent, TrainingConfig


async def run_unsloth(config: TrainingConfig, cancel) -> AsyncIterator[ProgressEvent]:  # pragma: no cover
    """Execute a real LoRA/QLoRA run. Requires unsloth/peft/transformers/trl +
    a CUDA GPU (guarded by UnslothProvider.is_available before this runs)."""
    import queue
    import threading

    from unsloth import FastLanguageModel  # type: ignore
    from transformers import TrainingArguments, TrainerCallback  # type: ignore
    from trl import SFTTrainer  # type: ignore
    from datasets import Dataset  # type: ignore

    load_in_4bit = config.method == "qlora"
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=config.base_model,
        max_seq_length=config.max_seq_length,
        load_in_4bit=load_in_4bit,
    )
    model = FastLanguageModel.get_peft_model(
        model, r=config.rank, lora_alpha=config.alpha, lora_dropout=config.dropout,
        random_state=config.seed,
    )

    # Records → a text dataset (expects {"text": ...} or instruction fields).
    def _to_text(rec):
        if isinstance(rec, dict):
            return rec.get("text") or "\n".join(str(v) for v in rec.values())
        return str(rec)

    ds = Dataset.from_dict({"text": [_to_text(r) for r in config.dataset_records]})

    events: "queue.Queue[ProgressEvent]" = queue.Queue()

    class _Bridge(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kw):
            if cancel():
                control.should_training_stop = True
            logs = logs or {}
            events.put(ProgressEvent(
                status="running", step=state.global_step,
                total_steps=state.max_steps, epoch=state.epoch or 0.0,
                total_epochs=config.epochs, loss=logs.get("loss"),
                val_loss=logs.get("eval_loss"), learning_rate=logs.get("learning_rate"),
            ))

    args = TrainingArguments(
        per_device_train_batch_size=config.batch_size,
        gradient_accumulation_steps=config.gradient_accumulation,
        warmup_steps=config.warmup_steps, num_train_epochs=config.epochs,
        learning_rate=config.learning_rate, lr_scheduler_type=config.scheduler,
        optim=config.optimizer, seed=config.seed,
        output_dir=config.output_dir or "outputs", logging_steps=1,
    )
    trainer = SFTTrainer(
        model=model, tokenizer=tokenizer, train_dataset=ds,
        dataset_text_field="text", max_seq_length=config.max_seq_length,
        args=args, callbacks=[_Bridge()],
    )

    done = threading.Event()

    def _train():
        try:
            trainer.train()
        finally:
            done.set()

    threading.Thread(target=_train, daemon=True).start()
    while not done.is_set() or not events.empty():
        try:
            yield events.get_nowait()
        except queue.Empty:
            await asyncio.sleep(0.1)

    trainer.save_model(config.output_dir or "outputs")
    yield ProgressEvent(status="completed", message="training complete")
