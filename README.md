# tokenspeed

**How fast is 30 tokens per second, really?**

Every local-LLM review brags about throughput — "47 tok/s on an M3," "180 tok/s on a 4090," "500 tok/s on Groq." The numbers are meaningless until you've watched them. Is 30 tok/s painfully slow? Comfortably readable? Faster than you can think? You can't tell from a benchmark table.

`tokenspeed` is a tiny terminal toy that streams fake "tokens" at any rate you set, so you can *feel* what those numbers mean. Bump the speed up and down with a keystroke and watch the cadence change in real time.

It can stream **syntax-highlighted pseudo-code** (because most of the time when speed matters, you're watching code stream out of an LLM) or **lorem ipsum text**. If you don't pick a mode on the command line, it'll ask.

## Run it

```bash
python3 tokenspeed.py                 # 30 tok/s, prompts for mode
python3 tokenspeed.py 60              # 60 tok/s, prompts for mode
python3 tokenspeed.py --mode code     # skip the prompt
python3 tokenspeed.py 120 --mode text # both at once
```

No dependencies — just Python 3 and a real terminal (the TUI uses raw-mode keyboard input and ANSI colors).

## Controls

| Key      | Action                                                              |
| -------- | ------------------------------------------------------------------- |
| `+` / `-`| Nudge the rate by ×1.25 (smooth across the whole range)             |
| `1`–`9`  | Jump to a preset: 5, 10, 20, 30, 60, 100, 200, 400, 800 tok/s       |
| `space`  | Pause / resume                                                      |
| `q`      | Quit                                                                |

## What to try

Start at the default `30` and read along. Then hit `1` (5 tok/s) — that's a Raspberry-Pi-class local model. Now `5` (60 tok/s) — typical hosted Claude or GPT. Then `7` (200 tok/s) — Groq territory. Then `9` (800 tok/s) — Cerebras-class, where the bottleneck is your eyeballs.

The token shapes mimic BPE output: short words/identifiers are one token, longer ones often split mid-word (`calculate_score` → `calc` + `ulate_score`), with operators and whitespace as their own tokens. So the visual rhythm at any given rate lands close to a real LLM streaming at the same rate.

## Why it's not "words per second"

LLMs don't emit words — they emit tokens, and English text averages roughly 1.3 tokens per word. A model running at 30 tok/s produces about 23 words/s. `tokenspeed` simulates the sub-word splits so a "30" here looks like a "30" from llama.cpp, not 30 whole words flying past.
