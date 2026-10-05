#!/usr/bin/env python3
"""rtl_check - find the right-to-left bugs that keep reaching production.

Scans CSS, HTML and component files (React, Vue, Svelte, Astro, PHP templates)
for patterns that break layouts in Hebrew, Arabic, Persian and Urdu: physical
left/right properties, Tailwind classes that do not flip, letter-spacing on
joined scripts, a missing dir on <html>, phone and e-mail inputs without
dir="ltr", and more. Standard library only, Python 3.8+.

Usage:
    python rtl_check.py [PATH ...] [--strict] [--json]

    PATH      files or directories (default: the current directory)
    --strict  also show hints, and fail on warnings as well as errors
    --json    print findings as JSON instead of text

Exit code: 1 when an error is found (with --strict, a warning too), else 0.

To accept one line on purpose, put this anywhere on it:  rtl-check: ignore
"""
import json
import os
import re
import sys

__version__ = "1.0.0"

SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", "out", ".next", ".nuxt",
    ".svelte-kit", ".turbo", ".cache", "vendor", "coverage", "__pycache__",
    ".venv", "venv", "env", ".output", "storybook-static",
}
CSS_EXT = {".css", ".scss", ".sass", ".less", ".pcss", ".styl"}
MARKUP_EXT = {".html", ".htm", ".vue", ".svelte", ".astro", ".php", ".erb",
              ".hbs", ".njk", ".liquid", ".twig", ".ejs"}
SCRIPT_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
ALL_EXT = CSS_EXT | MARKUP_EXT | SCRIPT_EXT
MAX_BYTES = 1_500_000
IGNORE = "rtl-check: ignore"

SIDE = {"left": "start", "right": "end"}
RTL_LANGS = r"(?:he|iw|yi|ar|fa|ur|ps|ckb|sd|ug|dv)"

# ---------------------------------------------------------------- CSS rules
# (rule id, severity, pattern, message, fix builder)
CSS_RULES = [
    ("css-physical-spacing", "error",
     re.compile(r"(?<![\w-])(margin|padding)-(left|right)\s*:"),
     "{0} stays on the same physical side in RTL",
     lambda m: "%s-inline-%s" % (m.group(1), SIDE[m.group(2)])),
    ("css-physical-border", "error",
     re.compile(r"(?<![\w-])border-(left|right)(-(?:width|style|color))?\s*:"),
     "{0} stays on the same physical side in RTL",
     lambda m: "border-inline-%s%s" % (SIDE[m.group(1)], m.group(2) or "")),
    ("css-physical-radius", "error",
     re.compile(r"(?<![\w-])border-(top|bottom)-(left|right)-radius\s*:"),
     "{0} does not flip in RTL",
     lambda m: "border-%s-%s-radius" % (
         "start" if m.group(1) == "top" else "end", SIDE[m.group(2)])),
    ("css-text-align", "error",
     re.compile(r"(?<![\w-])text-align\s*:\s*(left|right)\b"),
     "text-align: {1} keeps text on that side even when the page is RTL",
     lambda m: "text-align: %s" % SIDE[m.group(1)]),
    ("css-float", "error",
     re.compile(r"(?<![\w-])float\s*:\s*(left|right)\b"),
     "float: {1} does not flip in RTL",
     lambda m: "float: inline-%s" % SIDE[m.group(1)]),
    ("css-letter-spacing", "warn",
     re.compile(r"(?<![\w-])letter-spacing\s*:\s*(?=\S)"
                r"(?!(?:0(?![.\d])|normal|inherit|initial|unset|revert)\b)"
                r"(?!0(?:px|em|rem)?\s*[;}!\n])[^;}\n]+"),
     "letter-spacing pulls apart the joined letters of Arabic, Persian and "
     "Urdu (Hebrew is not joined)",
     lambda m: "scope it to Latin text, e.g. :lang(en) .title { ... }"),
    ("css-row-reverse", "warn",
     re.compile(r"(?<![\w-])flex-direction\s*:\s*row-reverse\b"),
     "flex rows already follow dir; reversing one 'for RTL' flips it twice",
     lambda m: "remove it and let dir order the row"),
]
# left/right as properties are only checked in stylesheets and style="",
# because in scripts a key called left or right is usually not CSS.
CSS_INSET = ("css-physical-inset", "warn",
             re.compile(r"(?<![\w.$-])(left|right)\s*:\s*(?=\S)(?!50%|auto\b)"),
             "{1} positions the element on the same side in RTL",
             lambda m: "inset-inline-%s" % SIDE[m.group(1)])
CSS_HINTS = [
    ("css-translate-x", "hint",
     re.compile(r"\btranslate(?:X|3d)?\(\s*-?[\d.]"),
     "transforms are physical: a slide-in from the left still comes from "
     "the left in RTL",
     lambda m: "mirror it under [dir=rtl] or use a logical inset"),
]

# JS style objects: camelCase properties
JS_RULES = [
    ("js-physical-style", "error",
     re.compile(r"(?<![\w$])(margin|padding)(Left|Right)\s*:"),
     "{0} is a physical side in a style object",
     lambda m: "%sInline%s" % (m.group(1), SIDE[m.group(2).lower()].title())),
    ("js-physical-style", "error",
     re.compile(r"(?<![\w$])border(Left|Right)(Width|Style|Color)?\s*:"),
     "{0} is a physical side in a style object",
     lambda m: "borderInline%s%s" % (SIDE[m.group(1).lower()].title(),
                                     m.group(2) or "")),
    ("js-text-align", "error",
     re.compile(r"(?<![\w$])textAlign\s*:\s*['\"](left|right)['\"]"),
     "textAlign: '{1}' keeps text on that side in RTL",
     lambda m: "textAlign: '%s'" % SIDE[m.group(1)]),
    ("js-letter-spacing", "warn",
     re.compile(r"(?<![\w$])letterSpacing\s*:\s*(?=\S)"
                r"(?!0(?![.\d])|['\"](?:0|normal)(?:px|em|rem)?['\"])"),
     "letterSpacing pulls apart the joined letters of Arabic, Persian and "
     "Urdu (Hebrew is not joined)",
     lambda m: "apply it only to Latin text"),
    ("html-viewport-zoom", "warn",
     re.compile(r"(?<![\w$])(?:maximumScale\s*:\s*1(?:\.0)?\b|"
                r"userScalable\s*:\s*false\b)"),
     "blocks pinch-zoom; small Arabic and Hebrew script needs it",
     lambda m: "remove maximumScale / userScalable"),
]

# ---------------------------------------------------------- Tailwind classes
CLASS_ATTR = re.compile(
    r"""(?:\bclass|\bclassName|:class|v-bind:class|class:list|\btw)\s*=\s*"""
    r"""(?:"([^"]*)"|'([^']*)'|\{\s*`([^`]*)`|\{\s*"([^"]*)"|\{\s*'([^']*)')""")
CLASS_CALL = re.compile(
    r"\b(?:cn|clsx|classnames|classNames|twMerge|twJoin|cva|tv)\s*\(")
STRING_LIT = re.compile(r"""["'`]([^"'`]*)["'`]""")

# A Tailwind scale value. Restricting to these keeps hand-written class names
# like "left-panel" out of the report. 1/2 and 50% are excluded on purpose:
# left-1/2 with -translate-x-1/2 centres an element, and "fixing" it to
# start-1/2 would push it off centre in RTL.
TW_VALUE = (r"(?!1/2$|\[50%\]$)(?:\d+(?:\.\d+)?|px|auto|full|\d+/\d+|"
            r"\[[^\]]+\]|\([^)]+\))")

TW_RULES = [
    (re.compile(r"^(-?)(m|p)(l|r)-(%s)$" % TW_VALUE), "error",
     lambda m: "%s%s%s-%s" % (m.group(1), m.group(2),
                              "s" if m.group(3) == "l" else "e", m.group(4))),
    (re.compile(r"^(-?)scroll-(m|p)(l|r)-(%s)$" % TW_VALUE), "error",
     lambda m: "%sscroll-%s%s-%s" % (m.group(1), m.group(2),
                                     "s" if m.group(3) == "l" else "e",
                                     m.group(4))),
    (re.compile(r"^(-?)(left|right)-(%s)$" % TW_VALUE), "error",
     lambda m: "%s%s-%s" % (m.group(1), SIDE[m.group(2)], m.group(3))),
    (re.compile(r"^text-(left|right)$"), "error",
     lambda m: "text-%s" % SIDE[m.group(1)]),
    (re.compile(r"^float-(left|right)$"), "error",
     lambda m: "float-%s (Tailwind v4) or a flex/grid layout"
     % SIDE[m.group(1)]),
    (re.compile(r"^rounded-(l|r|tl|tr|bl|br)(-.+)?$"), "error",
     lambda m: "rounded-%s%s" % (
         {"l": "s", "r": "e", "tl": "ss", "tr": "se",
          "bl": "es", "br": "ee"}[m.group(1)], m.group(2) or "")),
    (re.compile(r"^border-(l|r)(-.+)?$"), "error",
     lambda m: "border-%s%s" % ("s" if m.group(1) == "l" else "e",
                                m.group(2) or "")),
]
TW_WARN = [
    (re.compile(r"^space-x-(?!reverse$).+$"), "warn",
     "space-x-* was physical up to Tailwind v3 and needs rtl:space-x-reverse",
     "gap-x-* on the flex/grid parent works in every version"),
    (re.compile(r"^tracking-(?!normal$).+$"), "warn",
     "letter-spacing pulls apart the joined letters of Arabic, Persian and "
     "Urdu (Hebrew is not joined)",
     "add rtl:tracking-normal, or scope it: [&:lang(en)]:tracking-wide"),
    (re.compile(r"^flex-row-reverse$"), "warn",
     "flex rows already follow dir; reversing one 'for RTL' flips it twice",
     "remove it and let dir order the row"),
]
TW_MESSAGE = "{0} does not flip in RTL"

ICON_HINT = re.compile(
    r"\b(?:Arrow|Chevron|Caret)(?:Left|Right)\w*|"
    r"\b(?:arrow|chevron|caret)[-_](?:left|right)\b")

# ------------------------------------------------------------- HTML checks
HTML_OPEN = re.compile(r"<html\b", re.I)
META_OPEN = re.compile(r"<meta\b", re.I)
INPUT_OPEN = re.compile(r"<input\b", re.I)
STYLE_ATTR = re.compile(r"""\bstyle\s*=\s*(?:"([^"]*)"|'([^']*)')""")

# A rule whose selector already names a direction ([dir=rtl], :dir(ltr)) is
# direction-specific on purpose, so its physical sides are correct.
DIR_SCOPED = re.compile(r"\[dir\b|:dir\(", re.I)
# letter-spacing scoped to a non-RTL language (html[lang=en], :lang(en)) is the
# recommended fix, not the bug.
LATIN_SCOPED = re.compile(
    r"(?::lang\(\s*|\[lang[~|^]?=\s*['\"]?)(?!%s\b)[a-z]{2,3}\b" % RTL_LANGS,
    re.I)


def tag_text(text, start):
    """Return the tag that begins at text[start] ('<name ... >').

    Tracks quotes and JSX braces so an arrow function (=>) inside an
    attribute does not end the tag early.
    """
    depth, quote, i, n = 0, "", start + 1, len(text)
    while i < n:
        c = text[i]
        if quote:
            if c == quote:
                quote = ""
        elif c in "\"'`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        elif c == ">" and depth == 0:
            return text[start:i + 1]
        i += 1
    return text[start:]


def has_attr(tag, name):
    return re.search(r"(?<![\w:-])%s\s*=" % re.escape(name), tag, re.I)


def attr_value(tag, name):
    m = re.search(r"(?<![\w:-])%s\s*=\s*[\"'{]?\s*[\"']?([^\"'}\s>]*)"
                  % re.escape(name), tag, re.I)
    return m.group(1) if m else ""


# ---------------------------------------------------------------- scanning
class Finding(dict):
    __getattr__ = dict.get


def line_col(text, offset, starts):
    lo, hi = 0, len(starts) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1, offset - starts[lo] + 1


def class_strings(line):
    """Yield (column, class string) for class attributes and cn()/clsx()."""
    for m in CLASS_ATTR.finditer(line):
        for g in range(1, 6):
            if m.group(g) is not None:
                yield m.start(g), m.group(g)
    for m in CLASS_CALL.finditer(line):
        depth, i = 1, m.end()
        while i < len(line) and depth:
            if line[i] == "(":
                depth += 1
            elif line[i] == ")":
                depth -= 1
            i += 1
        for s in STRING_LIT.finditer(line, m.end(), i):
            yield s.start(1), s.group(1)


def check_classes(line):
    seen = set()
    for col, value in class_strings(line):
        value = re.sub(r"\$\{[^}]*\}", " ", value)
        for tm in re.finditer(r"\S+", value):
            raw = tm.group(0).strip(",{}").rstrip(":").strip("'\"")
            if not raw or (col, raw) in seen:
                continue
            seen.add((col, raw))
            parts = raw.split(":")
            variants, util = parts[:-1], parts[-1].lstrip("!")
            if any(v in ("rtl", "ltr") or v.startswith("[dir") for v in variants):
                continue  # already direction-specific on purpose
            prefix = ":".join(variants) + ":" if variants else ""
            for rx, sev, fix in TW_RULES:
                m = rx.match(util)
                if m:
                    yield (col + tm.start(), "tw-physical", sev,
                           TW_MESSAGE.format(raw), prefix + fix(m))
                    break
            else:
                for rx, sev, msg, fix in TW_WARN:
                    if rx.match(util):
                        rid = ("tw-letter-spacing" if util.startswith("tracking")
                               else "tw-row-reverse" if "reverse" in util
                               else "tw-space-x")
                        yield col + tm.start(), rid, sev, msg, fix
                        break


def scan_text(path, text, strict=False):
    ext = os.path.splitext(path)[1].lower()
    lines = text.split("\n")
    starts, pos = [], 0
    for ln in lines:
        starts.append(pos)
        pos += len(ln) + 1
    out = []

    def add(lineno, col, rule, sev, msg, fix):
        if sev == "hint" and not strict:
            return
        if IGNORE in lines[lineno - 1]:
            return
        out.append(Finding(file=path, line=lineno, col=col, rule=rule,
                           severity=sev, message=msg, fix=fix))

    css_rules = list(CSS_RULES) + (CSS_HINTS if strict else [])
    in_style = False
    for i, line in enumerate(lines, 1):
        opened = re.search(r"<style\b", line, re.I)
        if opened:
            in_style = True
        style_line = in_style
        if re.search(r"</style\s*>", line, re.I):
            in_style = False
        if IGNORE in line:
            continue
        dir_scoped = bool(DIR_SCOPED.search(line))
        latin_scoped = bool(LATIN_SCOPED.search(line))
        for rid, sev, rx, msg, fix in css_rules:
            if dir_scoped and sev == "error":
                continue
            if latin_scoped and rid == "css-letter-spacing":
                continue
            for m in rx.finditer(line):
                add(i, m.start() + 1, rid, sev,
                    msg.format(m.group(0).rstrip(": ").strip(),
                               *(g or "" for g in m.groups())), fix(m))
        inset_targets = []
        if ext in CSS_EXT or style_line:
            inset_targets.append((0, line))
        for sm in STYLE_ATTR.finditer(line):
            g = 1 if sm.group(1) is not None else 2
            inset_targets.append((sm.start(g), sm.group(g)))
        rid, sev, rx, msg, fix = CSS_INSET
        if dir_scoped:
            inset_targets = []
        for base, chunk in inset_targets:
            for m in rx.finditer(chunk):
                add(i, base + m.start() + 1, rid, sev,
                    msg.format(m.group(0), m.group(1)), fix(m))
        if ext in SCRIPT_EXT or ext in {".vue", ".svelte", ".astro"}:
            for rid, sev, rx, msg, fix in JS_RULES:
                for m in rx.finditer(line):
                    add(i, m.start() + 1, rid, sev,
                        msg.format(m.group(0).rstrip(": ").strip(),
                                   *(g or "" for g in m.groups())), fix(m))
        if ext not in CSS_EXT:
            for col, rid, sev, msg, fix in check_classes(line):
                add(i, col + 1, rid, sev, msg, fix)
            if strict:
                for m in ICON_HINT.finditer(line):
                    add(i, m.start() + 1, "icon-direction", "hint",
                        "%s points one way; mirror it in RTL if it means "
                        "back/next" % m.group(0),
                        "rtl:-scale-x-100 or [dir=rtl] .icon "
                        "{ transform: scaleX(-1) }")

    if ext in MARKUP_EXT or ext in SCRIPT_EXT:
        for m in HTML_OPEN.finditer(text):
            tag = tag_text(text, m.start())
            lang = attr_value(tag, "lang")
            if (re.match(RTL_LANGS + r"(?:[-_]|$)", lang, re.I)
                    and not has_attr(tag, "dir")):
                ln, col = line_col(text, m.start(), starts)
                add(ln, col, "html-dir", "error",
                    '<html lang="%s"> has no dir; the first paint is '
                    "left-to-right" % lang, 'add dir="rtl" in the static HTML')
        for m in META_OPEN.finditer(text):
            tag = tag_text(text, m.start())
            if not re.search(r"name\s*=\s*[\"']viewport", tag, re.I):
                continue
            if re.search(r"maximum-scale\s*=\s*1(?:\.0)?\b|"
                         r"user-scalable\s*=\s*(?:no|0)\b", tag, re.I):
                ln, col = line_col(text, m.start(), starts)
                add(ln, col, "html-viewport-zoom", "warn",
                    "the viewport blocks pinch-zoom; small Arabic and Hebrew "
                    "script needs it", "remove maximum-scale / user-scalable")
        for m in INPUT_OPEN.finditer(text):
            tag = tag_text(text, m.start())
            kind = attr_value(tag, "type").lower()
            if kind in ("tel", "email", "url") and not has_attr(tag, "dir"):
                ln, col = line_col(text, m.start(), starts)
                add(ln, col, "input-dir", "warn",
                    'type="%s" values are left-to-right and scramble on RTL '
                    "pages" % kind, 'add dir="ltr" to the input')
    return out


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
            continue
        for root, dirs, files in os.walk(p):
            dirs[:] = sorted(d for d in dirs
                             if d not in SKIP_DIRS and d != "__tests__")
            for f in sorted(files):
                low = f.lower()
                # minified bundles, and test files full of deliberate bad input
                if ".min." in low or ".test." in low or ".spec." in low:
                    continue
                if os.path.splitext(low)[1] in ALL_EXT:
                    yield os.path.join(root, f)


def scan_paths(paths, strict=False):
    findings, count = [], 0
    for path in iter_files(paths):
        try:
            if os.path.getsize(path) > MAX_BYTES:
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        count += 1
        findings.extend(scan_text(path, text, strict))
    return findings, count


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:  # a Windows console may not encode Hebrew/Arabic found in the code
        sys.stdout.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    if "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0
    if "--version" in argv:
        print("rtl_check", __version__)
        return 0
    strict = "--strict" in argv
    as_json = "--json" in argv
    paths = [a for a in argv if not a.startswith("--")] or ["."]
    findings, count = scan_paths(paths, strict)
    order = {"error": 0, "warn": 1, "hint": 2}
    findings.sort(key=lambda f: (f.file, f.line, f.col, order[f.severity]))
    if as_json:
        print(json.dumps(findings, indent=2, ensure_ascii=False))
    else:
        for f in findings:
            print("%s:%d:%d  %-5s  %-22s %s  ->  %s" % (
                f.file, f.line, f.col, f.severity, f.rule, f.message, f.fix))
        tally = {s: sum(1 for f in findings if f.severity == s) for s in order}
        print("rtl-check: %d error(s), %d warning(s)%s in %d file(s)" % (
            tally["error"], tally["warn"],
            ", %d hint(s)" % tally["hint"] if strict else "", count))
    failing = {"error", "warn"} if strict else {"error"}
    return 1 if any(f.severity in failing for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
