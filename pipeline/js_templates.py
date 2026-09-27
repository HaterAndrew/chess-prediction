"""Keep JavaScript template literals intact through minification.

rjsmin (1.2.5, the latest) minifies a template literal nested inside another
template's ${...} as if it were code: it drops the spaces in its text, so
`${done ? `${n}% range` : ''}` shipped as "80%range" and attributes ran
together ('class="a"id="b"'). protect() lifts every outermost template
literal out of the source behind a placeholder identifier, the minifier
never sees one, and restore() puts each back byte for byte.

The scanner knows strings, comments, regular expression literals (by the
token before the slash) and the ${...} nesting inside templates; that is all
it needs to find where each template starts and ends.
"""

PLACEHOLDER = "__BUNDLE_TPL_{}__"

# After one of these a slash starts a regular expression, not a division.
_REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^")
_REGEX_KEYWORDS = ("return", "typeof", "case", "delete", "void", "in", "of")


def _skip_string(src, i):
    quote = src[i]
    i += 1
    while i < len(src) and src[i] != quote:
        i += 2 if src[i] == "\\" else 1
    return i + 1


def _skip_regex(src, i):
    i += 1
    in_class = False
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "[":
            in_class = True
        elif c == "]":
            in_class = False
        elif c == "/" and not in_class:
            break
        i += 1
    i += 1
    while i < len(src) and src[i].isalpha():
        i += 1
    return i


def _skip_expr(src, i):
    """From just inside ${, to just past its closing brace."""
    depth = 1
    while i < len(src):
        c = src[i]
        if c in "'\"":
            i = _skip_string(src, i)
            continue
        if c == "`":
            i = _skip_template(src, i)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _skip_template(src, i):
    i += 1
    while i < len(src):
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            return i + 1
        if src.startswith("${", i):
            i = _skip_expr(src, i + 2)
            continue
        i += 1
    raise ValueError(f"unterminated template literal at offset {i}")


def _regex_allowed(src, i, prev):
    if prev is None or prev in _REGEX_AFTER:
        return True
    # After an identifier a slash divides, unless the word is a keyword that
    # takes an expression (return /x/.test(s)).
    j = len(src[:i].rstrip())
    k = j
    while k > 0 and (src[k - 1].isalnum() or src[k - 1] in "_$"):
        k -= 1
    return src[k:j] in _REGEX_KEYWORDS


def template_spans(src):
    """(start, end) of every outermost template literal in src."""
    spans, i, prev = [], 0, None
    while i < len(src):
        c = src[i]
        if c.isspace():
            i += 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            i = len(src) if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = len(src) if j < 0 else j + 2
        elif c in "'\"":
            i, prev = _skip_string(src, i), "a"
        elif c == "`":
            j = _skip_template(src, i)
            spans.append((i, j))
            i, prev = j, "a"
        elif c == "/" and _regex_allowed(src, i, prev):
            i, prev = _skip_regex(src, i), "a"
        else:
            i, prev = i + 1, c
    return spans


def protect(src):
    """src with each template literal behind a placeholder, and the literals."""
    literals, parts, last = [], [], 0
    for start, end in template_spans(src):
        parts.append(src[last:start])
        parts.append(PLACEHOLDER.format(len(literals)))
        literals.append(src[start:end])
        last = end
    parts.append(src[last:])
    return "".join(parts), literals


def restore(minified, literals):
    """Put each literal back; every placeholder must appear exactly once."""
    for n, literal in enumerate(literals):
        token = PLACEHOLDER.format(n)
        if minified.count(token) != 1:
            raise ValueError(f"{token} appears {minified.count(token)} times after minification")
        minified = minified.replace(token, literal)
    return minified
