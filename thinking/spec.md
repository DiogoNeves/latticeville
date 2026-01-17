# 🏘️ Latticeville - Spec

# Summary
Latticeville is a local-only experiment to build a tiny, simulated world with
AI-driven characters, inspired by the Generative Agents paper. The focus is a
small, clear loop: characters act, build memory, and produce emergent stories.
The UI is terminal-only (ASCII) and intentionally minimal. 🧱🤖

# Scope
The scope for this repo:
- Reproduce the core ideas of the Generative Agents paper in a tiny system.
- Build a fresh implementation (do not fix the original repo).
- Keep simulation logic separate from the viewer (terminal UI only).
- Keep visuals minimal (ASCII) and fully local.
- Build the first character(s), memory loop, and early emergent behavior.
- Defer any website or external showcase until later.

## Suggested 1–2 week scope (2h/day) ⏳
- Build only **one** character with a minimal memory loop.
- Add a **simple tick-based scheduler** (discrete time step).
- **ASCII-only** rendering via terminal.
- Implement just **one** behavioral variable (energy or curiosity).
- Optional: capture replay logs to a local file (no web UI yet).

# Goal 🎯
- Have “my own minions” running locally in a terminal UI.
- Understand memory systems deeply through a small, testable sim loop.
- Validate understanding by reproducing behaviors using my own prompts.
- Produce a progression narrative (notes or short videos).
- Keep the build playful, DIY, and local-first.

# Ideas 💡
- Fully ASCII visuals with small panels (world + context).
- Storytelling through first events: first character, first relationship, conflict.
- Daily/semi-daily logs forming a progression timeline.
- Include a brief “failed original repo” note as context.
- Title idea: *I built a village in my computer*.

# Notes 📝
- Original repo token system breaks — not worth fixing.
- Emphasize that the **main reason is to learn about memory**.
- Keep scope tight and avoid over-engineering.
- Keep everything local-only; no telemetry or network dependencies.

# References 🔗
- Paper Abstract: https://arxiv.org/abs/2304.03442
- Paper PDF: https://arxiv.org/pdf/2304.03442