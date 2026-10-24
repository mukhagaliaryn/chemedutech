"""Extract the three authorial lesson templates of the ICPAI guide (@S4-L1, @S4-L2, @S4-L3) into a Python data module.

    python3 docs/icpai/tools/gen_lessons.py docs/icpai/source/guide.md \\
        > apps/programme/management/commands/_icpai/lessons.py
    ruff format apps/programme/management/commands/_icpai/lessons.py

Each template: the header fields, the six stages «N-кезең. «Name» – X минут» with their blocks (a bold label and the text
under it, as HTML, verbatim) and the field of the lesson stage each block belongs to, the expected results and the
product. Numbering follows the guide's order 1/2/3 (the guide labels the first two «№2», SPEC О-9).
"""

import html
import pprint
import re
import sys

SECTIONS = [
    ("chem_design", "@S4-L1", "@S4-L2"),
    ("chem_detective", "@S4-L2", "@S4-L3"),
    ("chem_circuit", "@S4-L3", "@S4-AI"),
]
IMAGES = {
    "chem_design": ["image12.jpeg"],
    "chem_detective": ["image13.jpeg"],
    "chem_circuit": ["image14.jpeg", "image15.jpeg"],
}

# label → the field of a lesson stage (pedagogy.frames.STAGE_FIELDS); None → continues the previous block's field
FIELDS = {
    "Мұғалімнің әрекеті": "teacher_action",
    "Мұғалімнің бағыттаушы сұрақтары": "teacher_action",
    "Өндірістік тапсырма": "teacher_action",
    "Инженерлік тапсырма": "teacher_action",
    "Анодтағы тотығу реакциясы": "teacher_action",
    "Катодтағы тотықсыздану реакциясы": "teacher_action",
    "Жалпы реакция": "teacher_action",
    "Оқушының әрекеті": "student_task",
    "Оқушылардың әрекеті": "student_task",
    "Оқушының тапсырмасы": "student_task",
    "Оқушының міндеті": "student_task",
    "Авторлық тапсырма": "student_task",
    "Рефлексия сұрақтары": "student_task",
    "Химиялық шешім паспортының құрылымы": "student_task",
    "Химиялық паспорттың құрылымы": "student_task",
    "Энергия паспортының құрылымы": "student_task",
    "Авторлық ерекшелік": "methods",
    "Авторлық әдіс": "methods",
    "Кезең нәтижесі": "result",
    "Тапсырма": None,
    "Есептеу": None,
}
NUMBERED = {"тәжірибе": "experiment", "тапсырма": "student_task", "жағдаят": "student_task"}


def inline(text):
    text = text.replace("\\<", "\x00lt").replace("\\>", "\x00gt")
    text = re.sub(r"\\(.)", r"\1", text)
    keep = re.findall(r"</?(?:sub|sup)>", text)
    text = re.sub(r"</?(?:sub|sup)>", "\x01", text)
    text = html.escape(text, quote=False)
    for tag in keep:
        text = text.replace("\x01", tag, 1)
    text = text.replace("\x00lt", "&lt;").replace("\x00gt", "&gt;")
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)


def to_html(lines):
    out, items, kind = [], [], None

    def flush():
        nonlocal items, kind
        if items:
            out.append(f"<{kind}>" + "".join(f"<li>{i}</li>" for i in items) + f"</{kind}>")
        items, kind = [], None

    for line in lines:
        if not line:
            continue  # pandoc writes loose lists with blank lines between the items
        if m := re.match(r"^- (.+)$", line):
            if kind != "ul":
                flush()
                kind = "ul"
            items.append(inline(m.group(1)))
        elif m := re.match(r"^\d+\.\s+(.+)$", line):
            if kind != "ol":
                flush()
                kind = "ol"
            items.append(inline(m.group(1)))
        else:
            flush()
            out.append(f"<p>{inline(line)}</p>")
    flush()
    return "".join(out)


def field_value(lines, label):
    for line in lines:
        if m := re.match(rf"^\*\*{re.escape(label)}:\*\*\s*(.+)$", line):
            return inline(m.group(1).strip())
    return ""


def parse(text, code, tag, following):
    body = text[text.index(f"## [{tag}]") : text.index(f"## [{following}]")]
    lines = [line.strip() for line in body.splitlines()[1:]]
    lines = lines[: next(i for i, line in enumerate(lines) if line.startswith("<img"))]
    head_end = next(i for i, line in enumerate(lines) if re.match(r"^\*\*1-кезең\.", line))
    head = lines[:head_end]
    name = field_value(head, "Авторлық модель") or next(
        inline(line.strip("*")) for line in head if re.match(r"^\*\*«CHEM-", line)
    )
    feature_at = next((i for i, line in enumerate(head) if line.startswith("**Авторлық ерекшелігі:**")), None)
    feature = []
    if feature_at is not None:
        feature = [re.sub(r"^\*\*Авторлық ерекшелігі:\*\*\s*", "", head[feature_at])]
        feature += [line for line in head[feature_at + 1 :] if line]
    template = {
        "code": code,
        "name": name.strip("«»"),
        "topic": field_value(head, "Сабақ тақырыбы") or field_value(head, "Сабақтың тақырыбы"),
        "subject": field_value(head, "Пәні"),
        "grade": field_value(head, "Сыныбы"),
        "duration": field_value(head, "Сабақ ұзақтығы"),
        "technology": field_value(head, "Авторлық оқыту технологиясы"),
        "aim": field_value(head, "Сабақтың мақсаты"),
        "feature": to_html(feature),
        "images": IMAGES[code],
        "stages": [],
    }
    rest = lines[head_end:]
    outcomes_at = next(i for i, line in enumerate(rest) if "САБАҚТЫҢ КҮТІЛЕТІН НӘТИЖЕЛЕРІ" in line)
    tail, rest = rest[outcomes_at + 1 :], rest[:outcomes_at]
    product_at = next(i for i, line in enumerate(tail) if line.startswith("**Авторлық сабақтың негізгі"))
    template["outcomes"] = to_html(tail[:product_at])
    template["product"] = field_value(tail, "Авторлық сабақтың негізгі педагогикалық өнімі")

    stage, block = None, None
    for line in rest:
        if m := re.match(r"^\*\*(\d+)-кезең\.\s*«(.+?)»\s*[–-]\s*(\d+)\s*минут\*\*$", line):
            stage = {"n": int(m.group(1)), "title": m.group(2), "minutes": int(m.group(3)), "blocks": []}
            template["stages"].append(stage)
            block = None
            continue
        label_m = re.match(r"^\*\*([^*:]+?):(?:\s*(«[^*]+»))?\*\*\s*(.*)$", line)
        numbered_m = re.match(r"^\*\*(\d+)-(тәжірибе|тапсырма|жағдаят)\.\s*(.+?)\*\*$", line)
        if label_m and label_m.group(1) in FIELDS:
            label = label_m.group(1) + (f": {label_m.group(2)}" if label_m.group(2) else "")
            field = FIELDS[label_m.group(1)] or (block["field"] if block else "teacher_action")
            block = {"label": label, "field": field, "lines": [label_m.group(3)] if label_m.group(3) else []}
            stage["blocks"].append(block)
        elif numbered_m:
            block = {
                "label": f"{numbered_m.group(1)}-{numbered_m.group(2)}. {numbered_m.group(3)}",
                "field": NUMBERED[numbered_m.group(2)],
                "lines": [],
            }
            stage["blocks"].append(block)
        elif stage is not None and line:
            if block is None:
                raise SystemExit(f"{code} stage {stage['n']}: text before any label: {line!r}")
            block["lines"].append(line)
        elif block is not None:
            block["lines"].append(line)
    for stage in template["stages"]:
        for block in stage["blocks"]:
            block["html"] = to_html(block.pop("lines"))
    if len(template["stages"]) != 6 or sum(s["minutes"] for s in template["stages"]) != 45:
        raise SystemExit(f"{code}: {len(template['stages'])} stages")
    return template


def main(path):
    text = open(path, encoding="utf-8").read()
    templates = [parse(text, *s) for s in SECTIONS]
    print(
        '"""The three authorial lesson templates of section 4 (ICPAI guide @S4-L1, @S4-L2, @S4-L3) — generated verbatim from\n'
        "docs/icpai/source/guide.md: header fields, six stages with their labelled blocks (HTML) and the lesson-stage field\n"
        "each block belongs to, expected results, product. Do not edit by hand — regenerate with "
        'docs/icpai/tools/gen_lessons.py."""\n'
    )
    print("TEMPLATES = " + pprint.pformat(templates, width=118, sort_dicts=False))


if __name__ == "__main__":
    main(sys.argv[1])
