"""{{ message.content|ai_text }} — the AI's plain-text answer as safe HTML: paragraphs, «- » lists, **bold**."""

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()


def _inline(line: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(line))


@register.filter
def ai_text(text):
    blocks, items, para = [], [], []

    def flush():
        if para:
            blocks.append("<p>" + "<br>".join(para) + "</p>")
            para.clear()
        if items:
            blocks.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
            items.clear()

    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            flush()
        elif re.match(r"^[-•*]\s+", line):
            if para:
                blocks.append("<p>" + "<br>".join(para) + "</p>")
                para.clear()
            items.append(_inline(re.sub(r"^[-•*]\s+", "", line)))
        else:
            if items:
                blocks.append("<ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")
                items.clear()
            para.append(_inline(line))
    flush()
    return mark_safe("".join(blocks))  # every piece was escaped above
