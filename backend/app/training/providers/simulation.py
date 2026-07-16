"""Simulation training provider (default).

Runs a realistic LoRA/QLoRA training *loop* — decaying train/val loss, LR
schedule, steps/epochs, periodic checkpoints, ETA — with **no ML dependencies**.
This makes the entire Training Lab UX (wizard, live dashboard, checkpoints,
history, assistant) work offline on any machine.

It is honest about what it is: the backend name is ``simulation`` and the UI
labels runs accordingly. Swap in the ``unsloth`` provider for real training.
"""
from __future__ import annotations

import asyncio
import math
from typing import AsyncIterator

from app.training.providers.base import ProgressEvent, TrainingConfig, TrainingProvider


class SimulationProvider(TrainingProvider):
    name = "simulation"
    label = "Simulation (no GPU required)"

    # Wall-clock per step; kept small so a demo run finishes quickly.
    _step_delay = 0.05

    def is_available(self) -> tuple[bool, str]:
        return True, "always available (no ML stack or GPU required)"

    async def run(self, config: TrainingConfig, cancel) -> AsyncIterator[ProgressEvent]:
        n = max(1, len(config.dataset_records))
        eff_batch = max(1, config.batch_size * config.gradient_accumulation)
        steps_per_epoch = max(1, math.ceil(n / eff_batch))
        total_steps = steps_per_epoch * max(1, config.epochs)
        warmup = max(0, min(config.warmup_steps, total_steps))

        # Deterministic, seed-influenced starting loss.
        base_loss = 2.4 + (config.seed % 7) * 0.05
        checkpoint_every = max(1, total_steps // 4)
        best_val = math.inf

        yield ProgressEvent(status="running", total_steps=total_steps,
                            total_epochs=config.epochs, message="initializing (simulation)")

        for step in range(1, total_steps + 1):
            if cancel():
                yield ProgressEvent(status="cancelled", step=step, total_steps=total_steps,
                                    message="cancelled by user")
                return
            await asyncio.sleep(self._step_delay)

            epoch = step / steps_per_epoch
            # LR: linear warmup then cosine decay.
            if step <= warmup and warmup > 0:
                lr = config.learning_rate * step / warmup
            else:
                prog = (step - warmup) / max(1, total_steps - warmup)
                lr = config.learning_rate * 0.5 * (1 + math.cos(math.pi * prog))
            # Loss: exponential decay + tiny deterministic ripple.
            decay = math.exp(-3.0 * step / total_steps)
            ripple = 0.03 * math.sin(step * 1.3)
            loss = round(0.35 + (base_loss - 0.35) * decay + ripple, 4)
            val_loss = round(loss + 0.05 + 0.02 * math.sin(step * 0.7), 4)
            steps_per_sec = round(1.0 / self._step_delay, 2) if self._step_delay > 0 else None
            eta = round((total_steps - step) * self._step_delay, 1)

            checkpoint = None
            if step % checkpoint_every == 0 or step == total_steps:
                is_best = val_loss < best_val
                best_val = min(best_val, val_loss)
                checkpoint = {
                    "step": step, "epoch": round(epoch, 3),
                    "loss": loss, "val_loss": val_loss,
                    "path": f"{config.output_dir or 'checkpoints'}/step-{step}",
                    "is_best": 1 if is_best else 0,
                }

            yield ProgressEvent(
                status="running", step=step, total_steps=total_steps,
                epoch=round(epoch, 3), total_epochs=config.epochs,
                loss=loss, val_loss=val_loss, learning_rate=round(lr, 8),
                steps_per_sec=steps_per_sec, eta_seconds=eta,
                message=f"step {step}/{total_steps}", checkpoint=checkpoint,
            )

        yield ProgressEvent(status="completed", step=total_steps, total_steps=total_steps,
                            epoch=float(config.epochs), total_epochs=config.epochs,
                            message="training complete (simulation)")
