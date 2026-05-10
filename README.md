# tokenspeed

**How fast is 30 tokens per second, really?**

Every local-LLM review brags about throughput — "47 tok/s on an M3," "180 tok/s on a 4090," "500 tok/s on Groq." The numbers are meaningless until you've watched them. Is 30 tok/s painfully slow? Comfortably readable? Faster than you can think? You can't tell from a benchmark table.

`tokenspeed` is a tiny terminal toy that streams fake "tokens" at any rate you set, so you can *feel* what those numbers mean. Bump the speed up and down with a keystroke and watch the cadence change in real time.

Three modes:

- **`code`** — syntax-highlighted pseudo-code (Python/Rust/JS), the most common thing you watch stream out of an LLM
- **`text`** — lorem ipsum prose, for the chat/answer use case
- **`think`** — short dim-italic reasoning sentences alternating with code, mimicking how reasoning models stream their train of thought before they write or adapt code

If you don't pick a mode on the command line, it'll ask.

## Run it

```bash
python3 tokenspeed.py                  # 30 tok/s, prompts for mode
python3 tokenspeed.py 60               # 60 tok/s, prompts for mode
python3 tokenspeed.py --mode code      # skip the prompt
python3 tokenspeed.py 120 --mode think # both at once
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

Now switch modes (`--mode code` vs `--mode text`) at the same rate. The difference is striking and intentional — see below.

## What counts as a token

`tokenspeed` mimics how real BPE tokenizers (tiktoken, Claude's tokenizer, etc.) chunk content:

- Short words and identifiers are one token; longer ones often split mid-word (`calculate_score` → `calc` + `ulate_score`)
- Every `,` `.` `;` `:` is its own token — attached visually to the previous word, but ticking the rate clock on its own
- In code, every `(` `,` `:` `=` is also its own token, and a newline-plus-indentation run counts as one token too

That's why the same nominal rate feels very different across modes: 30 tok/s of code lands far less visible content per second than 30 tok/s of prose, because code is structurally dense in operators and indentation. The benchmark number is honest — the perceptual effect just varies a lot by content type, which is exactly the gap this tool exists to expose.

(English prose averages ~1.3 tokens per word, so 30 tok/s ≈ 23 words/s of text.)
