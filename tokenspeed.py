#!/usr/bin/env python3
"""Stream tokens at a configurable rate to feel LLM speeds."""
import argparse
import random
import re
import select
import sys
import termios
import time
import tty

# ---------------------------------------------------------------------------
# Prose mode (lorem ipsum)
# ---------------------------------------------------------------------------

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

PUNCT_EVERY = 12


def prose_tokens():
    i = 0
    while True:
        word = LOREM[i % len(LOREM)]
        i += 1
        suffix = ""
        if i % PUNCT_EVERY == 0:
            suffix = random.choice([",", ".", ".", ";"])
        if len(word) >= 6 and random.random() < 0.45:
            cut = random.randint(2, len(word) - 2)
            yield " " + word[:cut]
            yield word[cut:] + suffix
        else:
            yield " " + word + suffix


# ---------------------------------------------------------------------------
# Code mode (syntax-highlighted pseudo-code)
# ---------------------------------------------------------------------------

KEYWORDS = {
    "def", "class", "if", "else", "elif", "for", "while", "return", "import",
    "from", "as", "in", "not", "and", "or", "is", "None", "True", "False",
    "try", "except", "with", "pass", "break", "continue", "lambda", "yield",
    "async", "await", "fn", "let", "const", "mut", "pub", "struct", "impl",
    "match", "self", "Self", "use", "function", "var", "new", "throw",
}

BUILTINS = {
    "print", "len", "range", "sum", "min", "max", "sorted", "enumerate",
    "map", "filter", "zip", "list", "dict", "set", "tuple", "int", "str",
    "float", "bool", "open", "isinstance", "type", "Vec", "String", "Some",
    "Ok", "Err", "Result", "Option", "Error", "fetch", "Date", "Config",
    "fs",
}

DECL_KEYWORDS = {"def", "fn", "function", "class", "struct", "impl"}

COLORS = {
    "kw":      "\x1b[1;35m",   # bold magenta
    "builtin": "\x1b[36m",     # cyan
    "fn":      "\x1b[1;33m",   # bold yellow
    "string":  "\x1b[32m",     # green
    "number":  "\x1b[33m",     # yellow
    "comment": "\x1b[2;37m",   # dim
    "op":      "",
    "id":      "",
}
RESET = "\x1b[0m"

TOKEN_RE = re.compile(
    r"""
      (?P<comment> \#[^\n]* | //[^\n]* )
    | (?P<string>  "(?:[^"\\]|\\.)*" | '(?:[^'\\]|\\.)*' | `(?:[^`\\]|\\.)*` )
    | (?P<number>  \d+(?:\.\d+)? )
    | (?P<word>    [A-Za-z_][A-Za-z_0-9]* )
    | (?P<ws>      [ \t]+ | \n+ )
    | (?P<op>      [^\w\s] )
    """,
    re.VERBOSE,
)

CODE_SNIPPETS = [
    '''def estimate_tokens(text, model="claude-opus"):
    # Rough heuristic: ~1 token per 4 chars of English
    chars = len(text)
    overhead = sum(1 for c in text if c in ".,;:!?")
    return (chars // 4) + overhead + 1
''',
    '''class TokenStream:
    def __init__(self, model, prompt, rate=30):
        self.model = model
        self.prompt = prompt
        self.rate = rate
        self._budget = 2048

    async def __aiter__(self):
        async for chunk in self.model.stream(self.prompt):
            yield chunk.text
            if chunk.stop_reason:
                return
''',
    '''fn parse_config(path: &str) -> Result<Config, Error> {
    let contents = fs::read_to_string(path)?;
    let mut config = Config::default();
    for line in contents.lines() {
        if line.starts_with('#') || line.is_empty() {
            continue;
        }
        config.apply(line)?;
    }
    Ok(config)
}
''',
    '''const fetchUser = async (id) => {
    const res = await fetch(`/api/users/${id}`);
    if (!res.ok) {
        throw new Error(`HTTP ${res.status}: failed to load user`);
    }
    const user = await res.json();
    return { ...user, fetchedAt: Date.now() };
};
''',
    '''def merge_sorted(left, right):
    result = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    return result + left[i:] + right[j:]
''',
    '''def retry(func, attempts=3, backoff=0.5):
    # Exponential backoff with jitter
    for n in range(attempts):
        try:
            return func()
        except Exception as err:
            if n == attempts - 1:
                raise
            time.sleep(backoff * (2 ** n))
''',
]


def _color(text, kind):
    return f"{COLORS[kind]}{text}{RESET}" if COLORS[kind] else text


def _split_identifier(text):
    """BPE-ish: occasionally split long identifiers into two pieces."""
    if len(text) < 8 or random.random() < 0.4:
        yield text
        return
    boundaries = [i for i, c in enumerate(text)
                  if i > 1 and i < len(text) - 1 and (c == "_" or c.isupper())]
    cut = random.choice(boundaries) if boundaries else random.randint(3, len(text) - 3)
    yield text[:cut]
    yield text[cut:]


def code_tokens():
    snippets = list(CODE_SNIPPETS)
    random.shuffle(snippets)
    idx = 0
    while True:
        snippet = snippets[idx % len(snippets)]
        idx += 1
        if idx % len(snippets) == 0:
            random.shuffle(snippets)

        expecting_fn = False
        for m in TOKEN_RE.finditer(snippet):
            kind = m.lastgroup
            text = m.group()

            if kind == "ws":
                yield text
                continue

            if kind == "word":
                if text in KEYWORDS:
                    color = "kw"
                    expecting_fn = text in DECL_KEYWORDS
                elif text in BUILTINS:
                    color = "builtin"
                    expecting_fn = False
                elif expecting_fn:
                    color = "fn"
                    expecting_fn = False
                else:
                    color = "id"
            elif kind == "comment":
                color = "comment"
            elif kind == "string":
                color = "string"
            elif kind == "number":
                color = "number"
            else:
                color = "op"

            if color in ("id", "fn"):
                for piece in _split_identifier(text):
                    yield _color(piece, color)
            else:
                yield _color(text, color)

        yield "\n"


# ---------------------------------------------------------------------------
# TUI loop
# ---------------------------------------------------------------------------

PRESETS = {
    "1": 5, "2": 10, "3": 20, "4": 30, "5": 60,
    "6": 100, "7": 200, "8": 400, "9": 800,
}


def status(rate, paused, mode):
    state = "PAUSED" if paused else f"{rate:>5.1f} tok/s"
    return (
        f"\n\n\x1b[2m[ {state} | mode: {mode} | "
        f"+/- adjust · 1-9 preset · space pause · q quit ]\x1b[0m\n"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("rate", type=float, nargs="?", default=30.0,
                   help="initial tokens per second (default: 30)")
    p.add_argument("--mode", choices=["code", "prose"], default="code",
                   help="what to stream (default: code)")
    args = p.parse_args()

    rate = max(0.5, args.rate)
    paused = False
    gen = (code_tokens if args.mode == "code" else prose_tokens)()

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        sys.stdout.write(status(rate, paused, args.mode))
        sys.stdout.flush()

        next_tick = time.monotonic()
        for tok in gen:
            while select.select([sys.stdin], [], [], 0)[0]:
                ch = sys.stdin.read(1)
                if ch == "q":
                    sys.stdout.write(RESET + "\n\n")
                    return
                elif ch in ("+", "="):
                    rate = min(rate * 1.25, 2000)
                elif ch in ("-", "_"):
                    rate = max(rate / 1.25, 0.5)
                elif ch == " ":
                    paused = not paused
                elif ch in PRESETS:
                    rate = float(PRESETS[ch])
                else:
                    continue
                sys.stdout.write(status(rate, paused, args.mode))
                sys.stdout.flush()
                next_tick = time.monotonic()

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
                next_tick = time.monotonic()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        sys.stdout.write(RESET + "\n")


if __name__ == "__main__":
    main()
