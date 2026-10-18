"""Course content of the seed (in Kazakh — course content stored in the DB): the course, its modules, topic titles
and, for the topics whose materials are ready, a module with the stages (theory, quizzes; see t01.py).

The number of topics is not fixed: a new topic is a new line in TOPICS (and, when ready, a module in CONTENT).
"""

from . import t01

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
    2: (1, "VIIA тобының p-элементтері (галогендер)",
        "VIIA тобының p-элементтеріне жалпы сипаттама; галогендердің табиғатта таралуы, алынуы, физикалық және "
        "химиялық қасиеттері; галогендердің сутекті және оттекті қосылыстары."),
    3: (1, "VIA тобының p-элементтері",
        "VIA тобының p-элементтері; күкірттің табиғатта таралуы, алынуы, физикалық және химиялық қасиеттері."),
    4: (1, "VA тобының p-элементтеріне жалпы сипаттама",
        "VA тобының элементтері, табиғатта таралуы, физикалық және химиялық қасиеттері."),
    5: (1, "IVA тобының элементтері",
        "IVA тобының p-элементтеріне жалпы сипаттама, табиғатта таралуы, алынуы, физикалық және химиялық қасиеттері."),
}  # fmt: skip
TOPIC_COUNT = 15  # the skeleton; more topics may be added later
MODULE_1_TOPICS = 8  # topics 1–8 → module 1, the rest → module 2

CONTENT = {1: t01}
