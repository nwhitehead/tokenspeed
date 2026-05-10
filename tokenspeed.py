#!/usr/bin/env python3
"""Stream lorem-ipsum 'tokens' at a configurable rate to feel LLM speeds."""
import argparse
import random
import select
import sys
import termios
import time
import tty

LOREM = (
    "Lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor "
    "incididunt ut labore et dolore magna aliqua Ut enim ad minim veniam quis "
    "nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat "
    "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore "
    "eu fugiat nulla pariatur Excepteur sint occaecat cupidatat non proident sunt "
    "in culpa qui officia deserunt mollit anim id est laborum Sed ut perspiciatis "
    "unde omnis iste natus error sit voluptatem accusantium doloremque laudantium "
    "totam rem aperiam eaque ipsa quae ab illo inventore veritatis et quasi "
    "architecto beatae vitae dicta sunt explicabo Nemo enim ipsam voluptatem quia "
    "voluptas sit aspernatur aut odit aut fugit sed quia consequuntur magni "
    "dolores eos qui ratione voluptatem sequi nesciunt neque porro quisquam est "
    "qui dolorem ipsum quia dolor sit amet consectetur adipisci velit"
).split()

PUNCT_EVERY = 12  # roughly one comma/period every N words
PRESETS = {
    "1": 5, "2": 10, "3": 20, "4": 30, "5": 60,
    "6": 100, "7": 200, "8": 400, "9": 800,
}


def tokens():
    """Yield BPE-ish tokens: short words are one token, longer ones often split."""
    i = 0
    while True:
        word = LOREM[i % len(LOREM)]
        i += 1
        # Occasional punctuation, attached to previous token
        suffix = ""
        if i % PUNCT_EVERY == 0:
            suffix = random.choice([",", ".", ".", ";"])

        if len(word) >= 6 and random.random() < 0.45:
            cut = random.randint(2, len(word) - 2)
            yield " " + word[:cut]
            yield word[cut:] + suffix
        else:
            yield " " + word + suffix


def status(rate, paused):
    state = "PAUSED" if paused else f"{rate:>5.1f} tok/s"
    return f"\n\n\x1b[2m[ {state} | +/- adjust · 1-9 preset · space pause · q quit ]\x1b[0m\n"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("rate", type=float, nargs="?", default=30.0,
                   help="initial tokens per second (default: 30)")
    args = p.parse_args()

    rate = max(0.5, args.rate)
    paused = False

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write(status(rate, paused))
        sys.stdout.flush()

        next_tick = time.monotonic()
        gen = tokens()
        for tok in gen:
            # Drain any pending keypresses
            while select.select([sys.stdin], [], [], 0)[0]:
                ch = sys.stdin.read(1)
                if ch == "q":
                    sys.stdout.write("\n\n")
                    return
                elif ch in ("+", "="):
                    rate = min(rate * 1.25, 2000)
                    sys.stdout.write(status(rate, paused))
                    next_tick = time.monotonic()
                elif ch in ("-", "_"):
                    rate = max(rate / 1.25, 0.5)
                    sys.stdout.write(status(rate, paused))
                    next_tick = time.monotonic()
                elif ch == " ":
                    paused = not paused
                    sys.stdout.write(status(rate, paused))
                    next_tick = time.monotonic()
                elif ch in PRESETS:
                    rate = float(PRESETS[ch])
                    sys.stdout.write(status(rate, paused))
                    next_tick = time.monotonic()
                sys.stdout.flush()

            if paused:
                time.sleep(0.05)
                continue

            sys.stdout.write(tok)
            sys.stdout.flush()

            next_tick += 1.0 / rate
            sleep_for = next_tick - time.monotonic()
            if sleep_for > 0:
                time.sleep(sleep_for)
            else:
                # We fell behind (rate too high for terminal); resync
                next_tick = time.monotonic()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
