"""Course content of the seed (in Kazakh — course content stored in the DB): the course, its modules, topic titles
and, for the topics whose materials are ready, a module with the stages (theory, quizzes; see t01.py).

The number of topics is not fixed: a new topic is a new line in TOPICS (and, when ready, a module in CONTENT).
"""

from . import t01, t02, t03, t04

COURSE = {
    "slug": "chemistry",
    "title": "Бейорганикалық химия",
    "short_description": (
        "Болашақ химия мұғалімдеріне арналған бейорганикалық химия курсы: электрондық дәрістер, бейнедәрістер, "
        "виртуалды зертхана, практикалық жұмыстар және тесттер."
    ),
}

# (order, title)
MODULES = [
    (1, "Периодтық кестедегі s- және p-элементтердің жалпы сипаттамасы"),
    (2, "Периодтық кестедегі d- және f-элементтердің жалпы сипаттамасы"),
]

# number → (module order, title, summary); topics without ready materials stay unpublished placeholders
TOPICS = {
    1: (1, t01.TITLE, t01.SUMMARY),
    2: (1, t02.TITLE, t02.SUMMARY),
    3: (1, t03.TITLE, t03.SUMMARY),
    4: (1, t04.TITLE, t04.SUMMARY),
    5: (1, "IVA тобының элементтері",
        "IVA тобының p-элементтеріне жалпы сипаттама, табиғатта таралуы, алынуы, физикалық және химиялық қасиеттері."),
}  # fmt: skip
TOPIC_COUNT = 15  # the skeleton; more topics may be added later
MODULE_1_TOPICS = 8  # topics 1–8 → module 1, the rest → module 2

CONTENT = {1: t01, 2: t02, 3: t03, 4: t04}
