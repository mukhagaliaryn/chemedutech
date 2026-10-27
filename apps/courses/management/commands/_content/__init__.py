"""Course content of the seed (in Kazakh — course content stored in the DB): the course, its modules, topic titles
and, for the topics whose materials are ready, a module with the stages (theory, quizzes; see t01.py).

The number of topics is not fixed: a new topic is a new line in TOPICS (and, when ready, a module in CONTENT).
"""

from . import t01, t02, t03, t04, t05, t06, t07, t08, t09, t10

COURSE = {
    "slug": "chemistry",
    "title": "Химия",
    "short_description": (
        "Болашақ химия мұғалімдеріне арналған химия курсы: электрондық дәрістер, бейнедәрістер, "
        "виртуалды зертхана, практикалық жұмыстар және тесттер."
    ),
}
# ICPAI @S1: the course was renamed «Бейорганикалық химия» → «Жалпы химия» → «Химия» (the user, 2026-10-27); a course
# still under an old title gets the new one on the next seed (a title a teacher has changed is left alone)
LEGACY_TITLES = ("Бейорганикалық химия", "Жалпы химия")

# (order, title)
MODULES = [
    (1, "Теориялық бөлім"),
    (2, "Әдістемелік бөлім"),
]
# earlier module titles of the seed: a module still under one of them is renamed on the next seed (like LEGACY_TITLES)
LEGACY_MODULE_TITLES = (
    "Периодтық кестедегі s- және p-элементтердің жалпы сипаттамасы",
    "Периодтық кестедегі d- және f-элементтердің жалпы сипаттамасы",
)

# number → (module order, title, summary); topics without ready materials stay unpublished placeholders
TOPICS = {
    1: (1, t01.TITLE, t01.SUMMARY),
    2: (1, t02.TITLE, t02.SUMMARY),
    3: (1, t03.TITLE, t03.SUMMARY),
    4: (1, t04.TITLE, t04.SUMMARY),
    5: (1, t05.TITLE, t05.SUMMARY),
    6: (2, t06.TITLE, t06.SUMMARY),
    7: (2, t07.TITLE, t07.SUMMARY),
    8: (2, t08.TITLE, t08.SUMMARY),
    9: (2, t09.TITLE, t09.SUMMARY),
    10: (2, t10.TITLE, t10.SUMMARY),
}  # fmt: skip
TOPIC_COUNT = 10  # the course stays at 2 modules and 10 topics (the user, 2026-10-27); more may be added later
MODULE_1_TOPICS = 5  # topics 1–5 → module 1, the rest → module 2 (6–10 there too: the user's decision)

CONTENT = {1: t01, 2: t02, 3: t03, 4: t04, 5: t05, 6: t06, 7: t07, 8: t08, 9: t09, 10: t10}
