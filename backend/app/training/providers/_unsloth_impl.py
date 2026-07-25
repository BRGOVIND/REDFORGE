"""Real Unsloth LoRA/QLoRA recipe (GPU-only).

Isolated in its own module so the heavy imports happen only when a GPU + the ML
stack are present. Never imported in CI (no GPU). This is the concrete training
loop that :class:`UnslothProvider` delegates to; it translates HF Trainer
callbacks into :class:`ProgressEvent`s.

CONCURRENCY CONTRACT (RedForge is single-process asyncio — Constitution §8): every
blocking call here — the multi-GB ``from_pretrained`` download+load, PEFT wiring,
dataset tokenization, trainer construction, ``trainer.train()``, and ``save_model``
— runs on a **background thread**. The async generator only drains a queue and
``await``s, so the event loop is NEVER blocked and progress/health endpoints stay
responsive while a model downloads or trains. Each phase pushes a human-readable
``ProgressEvent`` so the user always sees what is happening (downloading, loading,
preparing, creating, training, saving) instead of an indefinite spinner.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

from app.training.providers.base import ProgressEvent, TrainingConfig


async def run_unsloth(config: TrainingConfig, cancel) -> AsyncIterator[ProgressEvent]:  # pragma: no cover
    """Execute a real LoRA/QLoRA run. Requires unsloth/peft/transformers/trl +
    a CUDA GPU (guarded by UnslothProvider.is_available before this runs).

    All heavy work happens on a worker thread; this coroutine only forwards the
    events the thread produces, so it never stalls the single-process event loop."""
    import queue
    import threading

    events: "queue.Queue[ProgressEvent]" = queue.Queue()
    done = threading.Event()
    # Capture the worker thread's real exception so it is SURFACED, not swallowed
    # (previously the true error — OOM, model-download failure — could be hidden and
    # replaced by a downstream save_model error).
    holder: dict = {"error": None}

    def _phase(message: str) -> None:
        events.put(ProgressEvent(status="running", message=message))

    def _work() -> None:
        try:
            # Defensive: guarantee the compiled-kernel cache is OUT of any watched
            # source tree BEFORE unsloth is imported here (the choke point where it is
            # first imported). app.main sets this at startup for every launcher; this
            # setdefault also covers direct/script imports that bypass app.main.
            import os as _os
            from pathlib import Path as _Path
            _cache = _os.environ.setdefault(
                "UNSLOTH_COMPILE_LOCATION",
                str(_Path.home() / ".cache" / "redforge" / "unsloth_compiled_cache"))
            try:
                _Path(_cache).mkdir(parents=True, exist_ok=True)
            except OSError:
                pass
            _phase(f"Loading training engine (torch + unsloth; cache -> {_cache})…")
            # Heavy imports happen on the thread too — importing torch/unsloth is
            # itself slow and must not block the loop.
            from unsloth import FastLanguageModel  # type: ignore
            from transformers import TrainingArguments, TrainerCallback  # type: ignore
            from trl import SFTTrainer  # type: ignore
            from datasets import Dataset  # type: ignore

            load_in_4bit = config.method == "qlora"
            # Instrumentation: prove the provider receives a foundation HF repo, not a
            # runtime tag. from_pretrained would raise HFValidationError on a tag.
            import logging as _logging
            _logging.getLogger("redforge.training-unsloth").info(
                "[model-id] provider: FastLanguageModel.from_pretrained(model_name=%r)", config.base_model)
            _phase(f"Downloading base model & tokenizer ({config.base_model})…")
            model, tokenizer = FastLanguageModel.from_pretrained(
                model_name=config.base_model,
                max_seq_length=config.max_seq_length,
                # dtype=None lets Unsloth pick the optimal compute dtype for the GPU
                # (bf16 on Ampere+, fp16 otherwise) — the documented default.
                dtype=None,
                load_in_4bit=load_in_4bit,
            )

            _phase("Attaching LoRA adapters…")
            model = FastLanguageModel.get_peft_model(
                model, r=config.rank, lora_alpha=config.alpha, lora_dropout=config.dropout,
                random_state=config.seed,
                # Unsloth's gradient checkpointing recomputes activations to cut VRAM
                # (its recommended setting) — the correct way to save memory, not CPU
                # offload. Pairs with the Hardware Compatibility Engine's safe defaults.
                use_gradient_checkpointing="unsloth",
            )

            # Records → a text dataset (expects {"text": ...} or instruction fields).
            def _to_text(rec):
                if isinstance(rec, dict):
                    return rec.get("text") or "\n".join(str(v) for v in rec.values())
                return str(rec)

            _phase("Preparing dataset…")
            ds = Dataset.from_dict({"text": [_to_text(r) for r in config.dataset_records]})

            # Track the most recent training state so a real checkpoint can be
            # persisted after training (the legacy runner persists a Checkpoint row
            # for any event carrying a ``checkpoint`` dict).
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
                # Disable the Trainer's OWN checkpoint saving. Its end-of-epoch save
                # calls torch.save(self.args), and Unsloth's dynamic patching makes
                # TRL's SFTConfig unpicklable ("Can't pickle SFTConfig: not the same
                # object") — which crashed the run right after the last step. We save
                # the LoRA adapter ourselves below via save_pretrained (no args pickle).
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
                # Save the PEFT adapter directly via save_pretrained rather than
                # trainer.save_model(): the latter also pickles training_args.bin, and
                # Unsloth's dynamic patching gives TRL's SFTConfig a class identity that
                # torch.save can't pickle ("Can't pickle SFTConfig: not the same
                # object"). save_pretrained writes adapter_config.json +
                # adapter_model.safetensors (+ tokenizer) — the actual artifact — with
                # no args pickling, so a completed run is saved reliably.
                import os as _os
                _os.makedirs(out_dir, exist_ok=True)
                model.save_pretrained(out_dir)
                try:
                    tokenizer.save_pretrained(out_dir)
                except Exception:  # noqa: BLE001 - tokenizer save is best-effort
                    pass
                # Emit a checkpoint event so the run persists a Checkpoint (artifact)
                # with the final metrics + adapter path — the Unsloth path previously
                # produced no checkpoints at all.
                events.put(ProgressEvent(
                    status="running", step=last["step"], total_steps=last["total_steps"],
                    epoch=last["epoch"], total_epochs=config.epochs, loss=last["loss"],
                    val_loss=last["val_loss"], message="Saved checkpoint (LoRA adapter)",
                    checkpoint={"step": last["step"], "epoch": last["epoch"],
                                "loss": last["loss"], "val_loss": last["val_loss"],
                                "path": out_dir, "is_best": 1},
                ))
            # Hand the final metrics to the terminal 'completed' event so the run's
            # stored metrics (final loss / steps) are populated, not left null.
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
        # Include the traceback HEAD (where the failure originates) as well as the
        # tail, so the real cause is visible instead of only the deepest frames.
        tb_view = tb if len(tb) <= 2200 else (tb[:900] + "\n…\n" + tb[-1200:])
        yield ProgressEvent(status="failed",
                            message=f"training error: {holder['error']}\n{tb_view}")
        return
    if cancel():
        yield ProgressEvent(status="cancelled", message="cancelled by user")
        return
    fin = holder.get("final") or {}
    yield ProgressEvent(status="completed", message="training complete",
                        step=fin.get("step", 0), total_steps=fin.get("total_steps", 0),
                        epoch=fin.get("epoch", 0.0), total_epochs=config.epochs,
                        loss=fin.get("loss"), val_loss=fin.get("val_loss"))
