"""HTML sanitising for rich text written in CKEditor 5 (ARCHITECTURE §9.2). Applied on output."""

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
