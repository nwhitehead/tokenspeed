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


def _bpe_split_plain_word(word):
    """BPE-ish: short words stay whole; longer words split more often."""
    n = len(word)
    if n <= 5:
        yield word
        return
    p_split = 0.3 if n <= 7 else 0.5 if n <= 10 else 0.75
    if random.random() >= p_split:
        yield word
        return
    cut = random.randint(2, n - 2)
    yield word[:cut]
    yield word[cut:]


def prose_tokens():
    i = 0
    while True:
        word = LOREM[i % len(LOREM)]
        i += 1
        first = True
        for piece in _bpe_split_plain_word(word):
            yield (" " + piece) if first else piece
            first = False
        if i % PUNCT_EVERY == 0:
            yield random.choice([",", ".", ".", ";"])


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
    | (?P<ws>      \n[ \t]* | [ \t]+ )
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


_IDENT_PARTS = re.compile(r"_+|[A-Z]+(?=[A-Z][a-z])|[A-Z][a-z]*|[a-z]+|\d+")


def _split_identifier(text):
    """BPE-ish: split identifiers at snake_case / camelCase / acronym boundaries."""
    if len(text) <= 5:
        yield text
        return

    chunks = _IDENT_PARTS.findall(text)
    # Single underscores cling to the following piece: `calculate_score` -> `calculate`, `_score`.
    # Runs of two or more (`__init__`) stand alone.
    merged = []
    i = 0
    while i < len(chunks):
        c = chunks[i]
        if c == "_" and i + 1 < len(chunks):
            merged.append("_" + chunks[i + 1])
            i += 2
        else:
            merged.append(c)
            i += 1

    if len(merged) > 1:
        yield from merged
        return

    if len(text) >= 10 and random.random() < 0.35:
        cut = random.randint(3, len(text) - 3)
        yield text[:cut]
        yield text[cut:]
    else:
        yield text


def _emit_snippet(snippet):
    """Yield colored tokens for one code snippet."""
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


def _snippet_cycle():
    snippets = list(CODE_SNIPPETS)
    random.shuffle(snippets)
    idx = 0
    while True:
        yield snippets[idx % len(snippets)]
        idx += 1
        if idx % len(snippets) == 0:
            random.shuffle(snippets)


def code_tokens():
    for snippet in _snippet_cycle():
        yield from _emit_snippet(snippet)
        yield "\n"


# ---------------------------------------------------------------------------
# Think mode (reasoning blended with code)
# ---------------------------------------------------------------------------

THINK_STYLE = "\x1b[2;3m"  # dim italic

THOUGHTS = [
    "Let me trace through this with a small example to make sure the indices line up.",
    "The function takes a path and returns a Result, so any IO error bubbles up via the ? operator.",
    "Wait — if the input list is empty, the loop never executes and we return a stale value.",
    "I think the cleanest approach is to extract this into its own helper and unit-test it in isolation.",
    "Actually, the existing utility already handles the retry logic, so I should just reuse it.",
    "Looking at the call sites, none of them pass None, so a non-optional type is fine here.",
    "Let me check whether the upstream library closes the connection on its own.",
    "First I'll validate the input, then run the main loop, then format the output for the caller.",
    "The hot path here is the inner loop, so I want to avoid allocations inside it if possible.",
    "I should add an early return when the cache is warm to skip the expensive recomputation.",
    "This is essentially a fold, so a reduce with an accumulator dictionary should work cleanly.",
    "If we're streaming, we can't materialize the whole list — switch to a generator that yields chunks.",
    "The error handling is duplicated across all three call sites, so let me factor it into a decorator.",
    "Hmm, the type annotation says str but the runtime value can be bytes when the encoding fails.",
    "I'll use a context manager so the file gets closed even if an exception is raised mid-iteration.",
    "Before writing the implementation, I want to sketch the public API to keep the surface minimal.",
    "The naming is a bit confusing here — result and response mean different things in this codebase.",
    "OK, I think I have a clear plan now. Let me write the function:",
    "That handles the happy path. Now I need to think about what happens on a partial failure.",
    "Reading the tests, the contract seems to be that empty input returns an empty list, not None.",
]


def _emit_thought():
    """Yield dim-italic tokens for a 3–7 sentence thought."""
    for s_idx in range(random.randint(3, 7)):
        sentence = random.choice(THOUGHTS)
        for word in sentence.split():
            base = word.rstrip(",.;:?!")
            tail = word[len(base):]
            if not base:
                base, tail = word, ""

            first = True
            for piece in _bpe_split_plain_word(base):
                prefix = " " if first else ""
                yield f"{THINK_STYLE}{prefix}{piece}{RESET}"
                first = False

            for ch in tail:
                yield f"{THINK_STYLE}{ch}{RESET}"


def think_tokens():
    for snippet in _snippet_cycle():
        yield from _emit_thought()
        yield "\n\n"
        yield from _emit_snippet(snippet)
        if random.random() < 0.7:
            yield "\n"
            yield from _emit_thought()
            yield "\n\n"
        else:
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


def prompt_mode():
    sys.stdout.write(
        "\n\x1b[1mChoose mode:\x1b[0m\n"
        "  \x1b[1;33m[c]\x1b[0m code   — syntax-highlighted pseudo-code\n"
        "  \x1b[1;33m[t]\x1b[0m text   — lorem ipsum prose\n"
        "  \x1b[1;33m[h]\x1b[0m think  — reasoning blended with code\n"
        "\n> "
    )
    sys.stdout.flush()
    keys = {"c": "code", "t": "text", "h": "think"}
    while True:
        ch = sys.stdin.read(1).lower()
        if ch in keys:
            sys.stdout.write(f"{keys[ch]}\n")
            return keys[ch]
        if ch in ("q", "\x03", "\x04"):  # q, Ctrl-C, Ctrl-D
            sys.stdout.write("\n")
            sys.exit(0)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("rate", type=float, nargs="?", default=30.0,
                   help="initial tokens per second (default: 30)")
    p.add_argument("--mode", choices=["code", "text", "think"], default=None,
                   help="what to stream (prompts if omitted)")
    args = p.parse_args()

    rate = max(0.05, args.rate)
    paused = False
    generators = {"code": code_tokens, "text": prose_tokens, "think": think_tokens}

    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)

        mode = args.mode or prompt_mode()
        gen = generators[mode]()

        sys.stdout.write(status(rate, paused, mode))
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
                    rate = max(rate / 1.25, 0.05)
                elif ch == " ":
                    paused = not paused
                elif ch in PRESETS:
                    rate = float(PRESETS[ch])
                else:
                    continue
                sys.stdout.write(status(rate, paused, mode))
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
