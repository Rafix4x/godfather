# Published agent system prompts

These are the agent system prompts published in
[elder-plinius/CL4R1T4S](https://github.com/elder-plinius/CL4R1T4S), kept here
so the counter-instructions in `scripts/payloads.py` can be checked against
the real wording of each agent's own configuration.

They are reference material, not runtime dependencies. Nothing in `scripts/`
reads these files at run time.

| File | Upstream path |
|:-----|:--------------|
| `claude-sonnet-3.7.txt` | `ANTHROPIC/Claude_Sonnet_3.7_New.txt` |
| `claude-opus-4.7.txt` | `ANTHROPIC/Claude-Opus-4.7.txt` |
| `claude-code.txt` | `ANTHROPIC/Claude_Code_03-04-24.md` |
| `codex.md` | `OPENAI/Codex.md` |
| `codex-sep-2025.md` | `OPENAI/Codex_Sep-15-2025.md` |
| `cursor.txt` | `CURSOR/Cursor_Prompt.md` |
| `cursor-2.0.txt` | `CURSOR/Cursor_2.0_Sys_Prompt.txt` |
| `cline.md` | `CLINE/Cline.md` |
| `gemini-2.5-pro.txt` | `GOOGLE/Gemini-2.5-Pro-04-18-2025.md` |
| `minimax.txt` | `MINIMAX/MiniMax.txt` |
| `kimi-k2-thinking.txt` | `MOONSHOT/Kimi_K2_Thinking.txt` |

## Provenance

`references/jailbreak-templates/` is derived the same way, from
[elder-plinius/L1B3RT4S](https://github.com/elder-plinius/L1B3RT4S), which
holds one jailbreak template per model family.

Both upstream projects are the source of every template in this repository.
They are credited in `LICENSE`. Anything derived from them keeps the same
terms.
