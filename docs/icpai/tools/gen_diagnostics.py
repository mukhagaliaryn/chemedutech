"""Extract the three diagnostic tests of the ICPAI guide (@S2-I, @S2-II, @S2-III) into a Python data module.

    python3 docs/icpai/tools/gen_diagnostics.py docs/icpai/source/guide.md \\
        > apps/programme/management/commands/_icpai/diagnostics.py

Questions «N\\. text», options «A\\) text», the answer key table «| N | A | Компонент |», the test title and aim,
the stage name and note (the marked lines) and the level table «| 0–4 | Төмен | … |» — all verbatim.
"""

import pprint
import re
import sys

COMPONENTS = {
    "Мотивациялық": "motivational",
    "Когнитивтік": "cognitive",
    "Іс-әрекеттік": "activity",
    "Рефлексивтік": "reflective",
}
LEVELS = {"Төмен": "low", "Орта": "medium", "Жоғары": "high"}


def section(text, tag, following):
    return text[text.index(f"## [{tag}]") : text.index(f"## [{following}]")]


def unmark(line):
    return re.sub(r'<span class="mark">(.*?)</span>', r"\1", line).strip()


def parse(text, tag, following):
    lines = [line.strip() for line in section(text, tag, following).splitlines()]
    questions, key, levels = [], {}, {}
    for line in lines:
        if m := re.match(r"^(\d+)\\\. (.+)$", line):
            questions.append({"n": int(m.group(1)), "text": m.group(2).strip(), "choices": []})
        elif (m := re.match(r"^([ABCD])\\\) (.+)$", line)) and questions:
            questions[-1]["choices"].append((m.group(1), m.group(2).strip()))
        elif m := re.match(r"^\|\s*(\d+)\s*\|\s*([ABCD])\s*\|\s*(\S+)\s*\|$", line):
            key[int(m.group(1))] = (m.group(2), COMPONENTS[m.group(3)])
        elif m := re.match(r"^\|\s*(0–4|5–7|8–10)\s*\|\s*(Төмен|Орта|Жоғары)\s*\|\s*(.+?)\s*\|$", line):
            levels[LEVELS[m.group(2)]] = m.group(3)
    title = next(line.split(":", 1)[1].strip() for line in lines if line.startswith(("Тест атауы:", "Тест тақырыбы:")))
    aim = next(line.split(":", 1)[1].strip() for line in lines if line.startswith("Мақсаты:"))
    marks = [unmark(line) for line in lines if line.startswith('<span class="mark">')]
    if len(questions) != 10:
        raise SystemExit(f"{tag}: {len(questions)} questions")
    out = []
    for q in questions:
        if len(q["choices"]) != 4:
            raise SystemExit(f"{tag} question {q['n']}: {len(q['choices'])} options")
        letter, component = key[q["n"]]
        out.append((q["text"], component, [(option, label == letter) for label, option in q["choices"]]))
    return {"stage": marks[0], "note": marks[1], "title": title, "aim": aim, "questions": out, "levels": levels}


def main(path):
    text = open(path, encoding="utf-8").read()
    tests = {
        "I": parse(text, "@S2-I", "@S2-II"),
        "II": parse(text, "@S2-II", "@S2-III"),
        "III": parse(text, "@S2-III", "@S3"),
    }
    print(
        '"""The three diagnostic tests of section 2 (ICPAI guide @S2-I, @S2-II, @S2-III) — generated verbatim from\n'
        "docs/icpai/source/guide.md: stage name and note, test title, aim, 10 questions with their 4 options in the "
        "guide's\norder (A–D), the correct option and the component from the answer key; level interpretations where "
        "the guide has\nthem (stage II has none). Do not edit by hand — regenerate with docs/icpai/tools/gen_diagnostics.py."
        '"""\n'
    )
    print("# phase → {stage, note, title, aim, questions: [(text, component, [(option, correct), …])], levels: {…}}")
    print("DIAGNOSTICS = " + pprint.pformat(tests, width=118, sort_dicts=False))


if __name__ == "__main__":
    main(sys.argv[1])
