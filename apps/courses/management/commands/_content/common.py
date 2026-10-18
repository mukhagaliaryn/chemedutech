"""Helpers for writing theory HTML: chemistry typed with Unicode indices becomes <sub>/<sup> markup."""

import re

_SUB = {c: str(i) for i, c in enumerate("₀₁₂₃₄₅₆₇₈₉")}
_SUP = {**{c: str(i) for i, c in enumerate("⁰¹²³⁴⁵⁶⁷⁸⁹")}, "⁺": "+", "⁻": "−"}


def chem(html: str) -> str:
    """«SO₄²⁻ + Ba²⁺» → «SO<sub>4</sub><sup>2−</sup> + Ba<sup>2+</sup>» (runs of indices stay together)."""
    html = re.sub("[₀-₉]+", lambda m: "<sub>" + "".join(_SUB[c] for c in m.group()) + "</sub>", html)
    return re.sub("[⁰¹²³⁴-⁹⁺⁻]+", lambda m: "<sup>" + "".join(_SUP[c] for c in m.group()) + "</sup>", html)


def eq(left, cond, right):
    """An equation line with the conditions written over the arrow."""
    return f'<p class="formula">{left} <span class="eq-cat"><span>{cond}</span>→</span> {right}</p>'


def formula(text):
    return f'<p class="formula">{text}</p>'


def fig(topic, name, alt, caption):
    return (
        f'<figure class="image"><img src="/static/content/{topic}/{name}.svg" alt="{alt}" width="560">'
        f"<figcaption>{caption}</figcaption></figure>"
    )


def table(head, rows):
    """A table from a header row and body rows (cells are HTML)."""
    th = "".join(f"<th>{c}</th>" for c in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f'<figure class="table"><table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></figure>'
