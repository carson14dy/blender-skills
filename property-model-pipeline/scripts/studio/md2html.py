"""Small, dependency-free Markdown -> HTML for the measurement report and its drop-in sections.

Covers what pm.py's report.md and the section files use: ATX headings, pipe tables (separator row optional, column
alignment from it), "- " / "* " / "1. " lists with one level of nesting, paragraphs, block quotes, horizontal rules,
fenced code, and inline **bold**, _italic_ / *italic*, `code`, [links](url) and ![images](src). Everything else is
escaped text: the converter never passes raw HTML through, and links are kept only for http(s), mailto and relative
targets.

    python3 md2html.py IN.md [OUT.html]      writes the HTML fragment (stdout without OUT)
"""
import html
import re
import sys

_TABLE_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_LIST = re.compile(r"^(\s*)([-*+]|\d{1,3}[.)])\s+(.*)$")
_HEAD = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_HR = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")


def _safe_url(u):
    u = u.strip()
    if re.match(r"^(https?:|mailto:)", u, re.I):
        return u
    if re.match(r"^[a-z][a-z0-9+.-]*:", u, re.I) or u.startswith("//"):
        return None                      # javascript:, data:, protocol-relative: dropped
    return u


def inline(t):
    """Inline markup on one line of text (escaped first, so the output is safe HTML)."""
    codes = []

    def keep_code(m):
        codes.append(html.escape(m.group(1), quote=False))
        return f"\x00{len(codes) - 1}\x00"

    t = re.sub(r"`([^`]+)`", keep_code, t)
    t = html.escape(t, quote=False)

    def img(m):
        src = _safe_url(html.unescape(m.group(2)))
        if not src:
            return m.group(1)
        return f'<img src="{html.escape(src)}" alt="{html.escape(html.unescape(m.group(1)))}">'

    def link(m):
        href = _safe_url(html.unescape(m.group(2)))
        if not href:
            return m.group(1)
        ext = ' target="_blank" rel="noopener"' if href.lower().startswith("http") else ""
        return f'<a href="{html.escape(href)}"{ext}>{m.group(1)}</a>'

    url = r"\(((?:[^()\s]|\([^()\s]*\))+)\)"          # one level of balanced parentheses in a URL
    t = re.sub(r"!\[([^\]]*)\]" + url, img, t)
    t = re.sub(r"\[([^\]]+)\]" + url, link, t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"(?<![\w*])_(?!\s)(.+?)(?<!\s)_(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"\x00(\d+)\x00", lambda m: f"<code>{codes[int(m.group(1))]}</code>", t)
    return t


def _cells(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", s)]


def _table(rows_txt):
    rows = [_cells(r) for r in rows_txt]
    align = []
    if len(rows_txt) > 1 and _TABLE_SEP.match(rows_txt[1].strip()):
        for c in rows[1]:
            align.append("right" if c.endswith(":") and not c.startswith(":") else
                         "center" if c.startswith(":") and c.endswith(":") else "")
        head, body = rows[0], rows[2:]
    else:
        head, body = None, rows

    def td(tag, c, i):
        a = align[i] if i < len(align) and align[i] else ""
        st = f' style="text-align:{a}"' if a else ""
        return f"<{tag}{st}>{inline(c)}</{tag}>"

    out = ['<div class="tw"><table>']
    if head:
        out.append("<thead><tr>" + "".join(td("th", c, i) for i, c in enumerate(head)) + "</tr></thead>")
    out.append("<tbody>" + "".join("<tr>" + "".join(td("td", c, i) for i, c in enumerate(r)) + "</tr>" for r in body)
               + "</tbody></table></div>")
    return "".join(out)


def _list(lines, i):
    """Parse a list starting at lines[i]; returns (html, next index). One nested level by indentation."""
    m = _LIST.match(lines[i])
    base = len(m.group(1).expandtabs(4))
    ordered = m.group(2)[0].isdigit()
    items = []                                    # [text, [nested lines]]
    while i < len(lines):
        ln = lines[i]
        m = _LIST.match(ln)
        if m and len(m.group(1).expandtabs(4)) <= base + 1:
            if m.group(2)[0].isdigit() != ordered and items:
                break
            items.append([m.group(3), []])
            i += 1
        elif m and items:                          # deeper list marker: nested item
            items[-1][1].append(ln)
            i += 1
        elif ln.strip() and items and (ln.startswith((" ", "\t"))) and not _HEAD.match(ln.strip()):
            if items[-1][1]:
                items[-1][1][-1] += " " + ln.strip()
            else:
                items[-1][0] += " " + ln.strip()   # lazy continuation of the item text
            i += 1
        else:
            break
    tag = "ol" if ordered else "ul"
    parts = []
    for text, sub in items:
        inner = inline(text)
        if sub:
            dedent = min(len(s) - len(s.lstrip()) for s in sub)
            inner += _list([s[dedent:] for s in sub], 0)[0]
        parts.append(f"<li>{inner}</li>")
    return f"<{tag}>" + "".join(parts) + f"</{tag}>", i


def convert(md, heading_offset=0):
    """Markdown text -> HTML fragment. heading_offset=1 turns '#' into <h2> (for sections inside a page)."""
    out, lines, i = [], md.replace("\r\n", "\n").split("\n"), 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        if not s:
            i += 1
            continue
        if _FENCE.match(ln):
            fence = _FENCE.match(ln).group(1)
            i += 1
            code = []
            while i < len(lines) and not lines[i].strip().startswith(fence):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(code), quote=False) + "</code></pre>")
        elif _HEAD.match(s) and not ln.startswith((" ", "\t")):
            m = _HEAD.match(s)
            n = min(6, len(m.group(1)) + heading_offset)
            out.append(f"<h{n}>{inline(m.group(2))}</h{n}>")
            i += 1
        elif _HR.match(s):                 # before lists: "* * *" is a rule, not an item
            out.append("<hr>")
            i += 1
        elif s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i])
                i += 1
            out.append(_table(rows))
        elif _LIST.match(ln):
            h, i = _list(lines, i)
            out.append(h)
        elif s.startswith(">"):
            q = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                q.append(lines[i].strip()[1:].lstrip())
                i += 1
            out.append("<blockquote>" + convert("\n".join(q), heading_offset) + "</blockquote>")
        else:
            para = []
            while i < len(lines):
                t = lines[i]
                ts = t.strip()
                if not ts or ts.startswith(("|", ">")) or _HEAD.match(ts) or _LIST.match(t) or _FENCE.match(t) \
                        or (_HR.match(ts) and para == []):
                    break
                para.append(ts)
                i += 1
            if not para:            # defensive: never loop on a line no branch consumes
                para.append(s)
                i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    with open(argv[0], encoding="utf-8") as f:
        h = convert(f.read())
    if len(argv) > 1:
        with open(argv[1], "w", encoding="utf-8") as f:
            f.write(h + "\n")
    else:
        sys.stdout.write(h + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
