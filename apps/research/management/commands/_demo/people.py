"""Made-up students: names, logins, passwords and the level each one works at."""

import secrets
from dataclasses import dataclass

MALE = [
    "Арман", "Нұрлан", "Ерлан", "Дәулет", "Әділет", "Бекзат", "Ерасыл", "Нұрсұлтан", "Темірлан", "Ақжол", "Мағжан",
    "Алмас", "Бауыржан", "Дархан", "Ерназар", "Жандос", "Қайрат", "Медет", "Нұрбол", "Олжас", "Рауан", "Саят",
    "Талғат", "Айдос",
]  # fmt: skip
FEMALE = [
    "Айгерім", "Аружан", "Дана", "Жансая", "Ақбота", "Әсем", "Балнұр", "Гүлназ", "Дильназ", "Еркеназ", "Жібек",
    "Інжу", "Қарлығаш", "Ләззат", "Меруерт", "Нұрай", "Перизат", "Сабина", "Томирис", "Ұлжан", "Аяулым", "Мадина",
    "Айша", "Зере",
]  # fmt: skip
SURNAME_ROOTS = [
    "Абдрахман", "Әбілқасым", "Байжан", "Бекмұхамбет", "Досжан", "Ерғали", "Жақсылық", "Жұмабек", "Кенжебек",
    "Қасым", "Құрманғали", "Мұхтар", "Нұрғали", "Оспан", "Сәрсенбай", "Серік", "Тоқтар", "Төлеген", "Шәкір",
    "Ысқақ", "Әміржан", "Бақыт", "Есен", "Жанат", "Мырзахмет", "Сағынтай",
]  # fmt: skip

# per group of 30: (level, how many) — everybody completes the course and ICPAI (the user, 2026-10-27); "progress"
# and "started" (students still at work) stay available for a later run
LEVELS = [("high", 10), ("medium", 12), ("low", 8)]
LEVEL_NAMES = {
    "high": "Толық · жоғары",
    "medium": "Толық · орта",
    "low": "Толық · төмен",
    "progress": "Процесте",
    "started": "Енді бастады",
}
# share of right answers: (from, to)
ACCURACY = {
    "high": (0.88, 0.97),
    "medium": (0.62, 0.75),
    "low": (0.36, 0.48),
    "progress": (0.6, 0.85),
    "started": (0.6, 0.8),
}

PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


@dataclass
class Student:
    number: int  # 1…60 → student01…student60
    first_name: str
    last_name: str
    level: str
    accuracy: float
    password: str

    @property
    def username(self) -> str:
        return f"student{self.number:02}"

    @property
    def email(self) -> str:
        return f"{self.username}@example.com"  # a reserved domain: no mail ever reaches anybody

    @property
    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name}"


def surname(root: str, female: bool) -> str:
    """Сағынтай → Сағынтаев / Сағынтаева; Нұрғали → Нұрғалиев; Оспан → Оспанов / Оспанова."""
    if root.endswith("й"):
        return root[:-1] + ("ева" if female else "ев")
    if root.endswith("и"):
        return root + ("ева" if female else "ев")
    return root + ("ова" if female else "ов")


def make_students(rng, groups: int = 2, per_group: int = 30) -> list[list[Student]]:
    """``groups`` lists of students with unique names, the levels of LEVELS shuffled inside each group
    (``per_group`` below 30 keeps the first ones — tests)."""
    used, result, number = set(), [], 0
    for _group in range(groups):
        levels = [level for level, count in LEVELS for _ in range(count)]
        rng.shuffle(levels)
        levels = levels[:per_group]
        students = []
        for level in levels:
            number += 1
            while True:
                female = rng.random() < 0.55
                first = rng.choice(FEMALE if female else MALE)
                last = surname(rng.choice(SURNAME_ROOTS), female)
                if (first, last) not in used:
                    used.add((first, last))
                    break
            low, high = ACCURACY[level]
            password = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(8))
            students.append(Student(number, first, last, level, round(rng.uniform(low, high), 3), password))
        result.append(students)
    return result
