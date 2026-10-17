"""HTML sanitising for rich text written in CKEditor 5 (ARCHITECTURE §9.2). Applied on output."""

import html as html_lib
import re

import nh3

ALLOWED_TAGS = {
    "a", "b", "blockquote", "br", "caption", "code", "col", "colgroup", "div", "em", "figcaption", "figure",
    "h2", "h3", "h4", "hr", "i", "img", "li", "mark", "oembed", "ol", "p", "pre", "s", "span", "strong", "sub",
    "sup", "table", "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul",
}  # fmt: skip
ALLOWED_ATTRIBUTES = {
    "*": {"class"},
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "width", "height", "srcset", "sizes"},
    "oembed": {"url"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan", "scope"},
    "ol": {"start", "reversed"},
}
URL_SCHEMES = {"http", "https", "mailto"}


def clean_html(html: str) -> str:
    """Strip scripts, event handlers, inline styles and unknown tags; keep chemistry markup (sub/sup)."""
    return nh3.clean(
        html or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=URL_SCHEMES,
        link_rel="noopener noreferrer",
    )


INLINE_TAGS = {"b", "br", "em", "i", "strong", "sub", "sup", "u", "s"}


def inline_html(html: str) -> str:
    """One-line rich text (an answer option): only inline marks; paragraphs from the editor become <br>."""
    text = re.sub(r"</p>\s*<p[^>]*>", "<br>", (html or "").strip())
    text = nh3.clean(text, tags=INLINE_TAGS, attributes={})
    return re.sub(r"^(?:\s|<br>|&nbsp;)+|(?:\s|<br>|&nbsp;)+$", "", text)


_SUB = str.maketrans("0123456789+-−=()", "₀₁₂₃₄₅₆₇₈₉₊₋₋₌₍₎")
_SUP = str.maketrans("0123456789+-−=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻⁼⁽⁾")


def html_to_text(html: str) -> str:
    """Rich text as plain text (for the AI and exports): H<sub>2</sub>O → H₂O, SO<sub>4</sub><sup>2-</sup> → SO₄²⁻,
    paragraphs and list items on their own lines. Plain text (older answers) comes back as it was."""
    if not html or "<" not in html:
        return html_lib.unescape(html or "")
    text = re.sub(r"<sub>(.*?)</sub>", lambda m: m.group(1).translate(_SUB), html, flags=re.S | re.I)
    text = re.sub(r"<sup>(.*?)</sup>", lambda m: m.group(1).translate(_SUP), text, flags=re.S | re.I)
    text = re.sub(r"<li[^>]*>", "\n• ", text, flags=re.I)
    text = re.sub(r"<br\s*/?>|</p>|</h\d>|</tr>|</ul>|</ol>", "\n", text, flags=re.I)
    text = html_lib.unescape(re.sub(r"<[^>]+>", "", text)).replace("\xa0", " ")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in text.splitlines())).strip()
