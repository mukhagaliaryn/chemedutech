"""Chemical formula and equation parser (ARCHITECTURE §3.6). Pure Python, no Django.

    parse_formula("Ca(OH)2")          → Formula: {Ca: 1, O: 2, H: 2}, charge 0
    parse_formula("CuSO4·5H2O")       → hydrate, water counted in
    parse_formula("SO4^2-")           → charge −2 (also "SO42-", "SO₄²⁻", "SO4 2-")
    parse_equation("Zn + 2HCl -> ZnCl2 + H2↑")
    compare_equations(expected, given) → EquationCheck(same_species, same_coefficients, multiple, balanced)

Rules for students' input: Unicode subscripts are digits (₂ = 2), spaces are ignored, letter case
matters (Co ≠ CO), the arrow may be = -> → ⇌, ↑ ↓ and state marks (g) (aq) (s) (l) are ignored.
Words around the answer are ignored: «Жауабы: Zn + 2HCl = ZnCl2 + H2.» and «ZnCl2 — мырыш хлориді» read as the
equation / formula alone (the chemistry is the run of Latin symbols, digits and signs that holds the arrow).
A charge is written after the formula: Zn2+, OH-, Fe+++, SO4^2-. A single digit before the sign is the
charge of a one-element ion (Zn2+, Fe3+) or after "]" ([Fe(CN)6]4-) and a count in a polyatomic ion
(NH4+, H3O+, NO3-); with two digits the last one is the charge (SO42- = SO₄²⁻). Use ^ when in doubt:
O2^- is the superoxide ion, O^2- the oxide ion.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from functools import reduce
from math import gcd

ELEMENTS = frozenset(
    """H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr
    Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu
    Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg
    Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og""".split()
)

_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
_SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻", "0123456789+-")
_SUPERSCRIPT_CHARS = set("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")
_DASHES = str.maketrans({"−": "-", "–": "-", "—": "-", "‐": "-"})
_HYDRATE_SPLIT = re.compile(r"[·•∙⋅*]|\.(?=\d*[A-Z(\[])")
_ARROW = re.compile(r"<=>|<->|⇌|⇄|⟷|->|→|⟶|=>|==|=")
_STATE = re.compile(r"\((?:s|l|g|aq|т|с|г|қ|ер)\)")
# Conditions are not substances: a catalyst or heating written next to the arrow or at the very end:
# "2H2O2 →(MnO2) 2H2O + O2", "2KMnO4 →t° K2MnO4 + …", "2H2O2 → 2H2O + O2 (MnO2)".
_AFTER_ARROW = re.compile(r"^\s*(?:\([^()]*\)|\[[^\[\]]*\]|t°?|°)\s*")
_TRAILING_CONDITION = re.compile(r"\s+(?:\([^()]*\)|\[[^\[\]]*\])\s*$")
_CHARGE = re.compile(r"\d[+-]|[+-]\d|[+-]+")


class ChemError(ValueError):
    """Input that cannot be read. ``code`` is stable (for messages), ``detail`` names the culprit."""

    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


# --- formulas ----------------------------------------------------------------


@dataclass(frozen=True)
class Formula:
    text: str  # as written, normalised (subscripts → digits, no spaces)
    composition: tuple[tuple[str, int], ...]  # sorted (element, count)
    charge: int = 0

    @property
    def counts(self) -> dict[str, int]:
        return dict(self.composition)

    @property
    def key(self) -> tuple:
        """Identity used for comparison: what the species is made of, not how it is written."""
        return (self.composition, self.charge)

    def pretty(self) -> str:
        return pretty_formula(self.text, self.charge)


def _parse_charge(token: str) -> int:
    sign = -1 if "-" in token else 1
    digits = re.sub(r"[+-]", "", token)
    if digits:
        if len(token) - len(digits) != 1:
            raise ChemError("bad_charge", token)
        value = int(digits)
    else:
        value = len(token)
    if value == 0:
        raise ChemError("bad_charge", token)
    return sign * value


def _split_charge(s: str) -> tuple[str, int]:
    """Separate a trailing charge from the formula body."""
    if any(ch in _SUPERSCRIPT_CHARS for ch in s):
        m = re.fullmatch(r"([^⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)([⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)", s)
        if not m:
            raise ChemError("bad_charge", s)
        return m.group(1), _parse_charge(m.group(2).translate(_SUPERSCRIPTS))
    if "^" in s:
        body, _, charge = s.partition("^")
        if not _CHARGE.fullmatch(charge.strip()):
            raise ChemError("bad_charge", charge)
        return body, _parse_charge(charge.strip())
    m = re.fullmatch(r"(.*\S)\s+(\d[+-]|[+-]\d?|[+-]+)", s)  # "SO4 2-"
    if m:
        return m.group(1), _parse_charge(m.group(2))
    m = re.fullmatch(r"(.*?)(\d*)([+-]+)", s)  # "Zn2+", "NH4+", "SO42-", "OH-", "Fe+++"
    if not m:
        return s, 0
    body, digits, signs = m.groups()
    if not digits:
        return body, _parse_charge(signs)
    if len(signs) > 1:
        raise ChemError("bad_charge", digits + signs)
    if len(digits) >= 2:  # SO42-, PO43-, Cr2O72-, Hg22+: the last digit is the charge
        return body + digits[:-1], _parse_charge(digits[-1] + signs)
    if body.endswith("]") or re.fullmatch(r"[A-Z][a-z]?", body.strip()):  # Zn2+, Fe3+, [Fe(CN)6]4-
        return body, _parse_charge(digits + signs)
    return body + digits, _parse_charge(signs)  # NH4+, H3O+, NO3-: the digit is a count


class _Reader:
    def __init__(self, text: str):
        self.s, self.i = text, 0

    def peek(self) -> str:
        return self.s[self.i] if self.i < len(self.s) else ""

    def number(self) -> int | None:
        start = self.i
        while self.peek().isdigit():
            self.i += 1
        if start == self.i:
            return None
        value = int(self.s[start : self.i])
        if value == 0:
            raise ChemError("zero_count", self.s)
        return value

    def group(self, closing: str = "") -> Counter:
        total: Counter = Counter()
        while self.i < len(self.s):
            ch = self.peek()
            if ch in "([":
                self.i += 1
                inner = self.group(")" if ch == "(" else "]")
                if self.peek() != (")" if ch == "(" else "]"):
                    raise ChemError("unbalanced_brackets", self.s)
                self.i += 1
                if not inner:
                    raise ChemError("empty_brackets", self.s)
                n = self.number() or 1
                for el, c in inner.items():
                    total[el] += c * n
            elif ch in ")]":
                if not closing:
                    raise ChemError("unbalanced_brackets", self.s)
                return total
            elif ch.isupper():
                symbol = ch
                self.i += 1
                if self.peek().islower():
                    symbol += self.peek()
                    self.i += 1
                if symbol not in ELEMENTS:
                    raise ChemError("unknown_element", symbol)
                total[symbol] += self.number() or 1
            elif ch.islower():
                raise ChemError("lowercase_element", self.s[self.i :])
            else:
                raise ChemError("unexpected_symbol", ch)
        if closing:
            raise ChemError("unbalanced_brackets", self.s)
        return total


def _normalize(text: str) -> str:
    return str(text or "").translate(_SUBSCRIPTS).translate(_DASHES).strip()


# Characters chemistry is written with; anything else (Cyrillic words, «:», «!», quotes …) is commentary.
_CHEM_RUN = re.compile(r"[A-Za-z0-9\s+\-=<>→⇌⇄⟷⟶↑↓()\[\]{}^·•∙⋅*°.,⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+")
_EDGE_PUNCT = " \t\n.,;"
_WORDS_IN_BRACKETS = re.compile(r"[(\[][^()\[\]]*[^\x00-\x7f₀-₉⁰-⁹⁺⁻→⇌⇄⟷⟶↑↓·•∙⋅°][^()\[\]]*[)\]]")
_SPACED_DASH = re.compile(r"\s-\s")  # «ZnCl2 — мырыш хлориді»: a dash between spaces separates words


def _strip_prose(s: str, need_arrow: bool) -> str:
    """The chemistry inside an answer with words around it: the one run with the arrow (an equation) or with a
    capital letter (a formula), without the full stop or comma that ends a sentence. With two such runs
    («H2$O») nothing is guessed: the input stays as typed and is reported as unreadable."""
    if not _CHEM_RUN.fullmatch(s):
        s = _WORDS_IN_BRACKETS.sub(" ", s)  # «(катализатор)», «(ақ тұнба)»
        runs = [r for m in _CHEM_RUN.finditer(s) for r in _SPACED_DASH.split(m.group())]
        runs = [r for r in runs if (_ARROW.search(r) if need_arrow else re.search(r"[A-Z]", r))]
        if len(runs) == 1:
            s = runs[0]
    return s.strip(_EDGE_PUNCT)


def parse_formula(text: str) -> Formula:
    s = _strip_prose(_normalize(text), need_arrow=False)
    if not s:
        raise ChemError("empty")
    body, charge = _split_charge(s)
    body = re.sub(r"\s+", "", body)
    if not body:
        raise ChemError("empty")
    if body[0].isdigit():
        raise ChemError("leading_coefficient", body)
    total: Counter = Counter()
    for index, part in enumerate(_HYDRATE_SPLIT.split(body)):
        if not part:
            raise ChemError("bad_hydrate", body)
        m = re.match(r"\d+", part)
        multiplier = 1
        if m:
            if index == 0:
                raise ChemError("leading_coefficient", part)
            multiplier = int(m.group())
            part = part[m.end() :]
        reader = _Reader(part)
        counts = reader.group()
        if not counts:
            raise ChemError("empty", part)
        for el, c in counts.items():
            total[el] += c * multiplier
    canonical = body + (f"^{abs(charge) if abs(charge) > 1 else ''}{'+' if charge > 0 else '-'}" if charge else "")
    return Formula(canonical, tuple(sorted(total.items())), charge)


def formulas_equal(expected: str | Formula, given: str) -> bool:
    """Same elements, counts and charge; how it is written does not matter. Unreadable input → False."""
    try:
        exp = expected if isinstance(expected, Formula) else parse_formula(expected)
        return exp.key == parse_formula(given).key
    except ChemError:
        return False


# --- equations ---------------------------------------------------------------


@dataclass(frozen=True)
class Term:
    coefficient: int
    formula: Formula


@dataclass(frozen=True)
class Equation:
    reactants: tuple[Term, ...]
    products: tuple[Term, ...]
    reversible: bool = False

    @staticmethod
    def _side_atoms(side) -> Counter:
        atoms: Counter = Counter()
        for t in side:
            for el, c in t.formula.composition:
                atoms[el] += c * t.coefficient
        return atoms

    @staticmethod
    def _side_charge(side) -> int:
        return sum(t.coefficient * t.formula.charge for t in side)

    @property
    def atoms_balanced(self) -> bool:
        return self._side_atoms(self.reactants) == self._side_atoms(self.products)

    @property
    def charge_balanced(self) -> bool:
        return self._side_charge(self.reactants) == self._side_charge(self.products)

    @property
    def is_balanced(self) -> bool:
        return self.atoms_balanced and self.charge_balanced

    @property
    def is_reduced(self) -> bool:
        """Coefficients have no common divisor (2H2 + O2, not 4H2 + 2O2)."""
        return reduce(gcd, (t.coefficient for t in (*self.reactants, *self.products))) == 1

    @staticmethod
    def _merged(side) -> dict[tuple, int]:
        merged: dict[tuple, int] = {}
        for t in side:
            merged[t.formula.key] = merged.get(t.formula.key, 0) + t.coefficient
        return merged

    def sides(self) -> tuple[dict[tuple, int], dict[tuple, int]]:
        """{species key: total coefficient} for both sides — order and repeats do not matter."""
        return self._merged(self.reactants), self._merged(self.products)

    def pretty(self) -> str:
        def side(terms):
            return " + ".join(f"{t.coefficient if t.coefficient > 1 else ''}{t.formula.pretty()}" for t in terms)

        return f"{side(self.reactants)} {'⇌' if self.reversible else '→'} {side(self.products)}"


def _split_terms(side: str) -> list[str]:
    """Split one side on "+" signs that separate substances, not charges."""
    side = side.strip()
    if not side:
        raise ChemError("empty_side")
    if re.search(r"\s\+$", side) or re.match(r"^\+\s", side):  # "H2 + ->": a dangling separator
        raise ChemError("empty_term", side)
    if re.search(r"\s\+\s", side):  # spaced pluses separate terms: "Zn2+ + 2H+"
        parts = re.split(r"\s+\+\s+", side)
    else:  # "Zn+2HCl": a plus followed by a coefficient, an element or a bracket
        parts = re.split(r"\+(?=\s*[\dA-Z(\[])", side)
    parts = [p.strip() for p in parts]
    if any(not p for p in parts):
        raise ChemError("empty_term", side)
    return parts


def _parse_term(text: str) -> Term:
    m = re.fullmatch(r"(\d+)?\s*(.+)", text.strip())
    coefficient = int(m.group(1)) if m.group(1) else 1
    if coefficient == 0:
        raise ChemError("zero_coefficient", text)
    return Term(coefficient, parse_formula(m.group(2)))


def parse_equation(text: str) -> Equation:
    s = _normalize(text)
    s = _STATE.sub(" ", s)  # before the words are cut: state marks may be Kazakh — (г), (ер)
    s = _strip_prose(s, need_arrow=True)
    s = s.replace("↑", " ").replace("↓", " ")
    arrows = list(_ARROW.finditer(s))
    if not arrows:
        raise ChemError("no_arrow", s)
    if len(arrows) > 1:
        raise ChemError("many_arrows", s)
    arrow = arrows[0]
    left, right = s[: arrow.start()], _AFTER_ARROW.sub("", s[arrow.end() :])
    right = _TRAILING_CONDITION.sub("", right)
    reactants = tuple(_parse_term(t) for t in _split_terms(left))
    products = tuple(_parse_term(t) for t in _split_terms(right))
    return Equation(reactants, products, reversible=arrow.group() in ("<=>", "<->", "⇌", "⇄", "⟷"))


@dataclass(frozen=True)
class EquationCheck:
    same_species: bool  # the same substances on each side (order and repeats do not matter)
    same_coefficients: bool  # … with exactly the same coefficients
    multiple: Fraction | None  # given = multiple × expected (≠ 1), e.g. 4H2 + 2O2 → 4H2O gives 2
    balanced: bool  # the given equation balances atoms and charge
    reduced: bool  # the given coefficients have no common divisor

    @property
    def is_exact(self) -> bool:
        return self.same_species and self.same_coefficients

    @property
    def balanced_not_reduced(self) -> bool:
        """«Balanced but not reduced»: right substances, balanced, coefficients a multiple of the answer."""
        return self.same_species and self.balanced and self.multiple is not None and not self.reduced


def _ratio(expected: dict, given: dict) -> Fraction | None:
    ratios = {Fraction(given[k], expected[k]) for k in expected}
    return ratios.pop() if len(ratios) == 1 else None


def compare_equations(expected: str | Equation, given: str | Equation) -> EquationCheck:
    exp = expected if isinstance(expected, Equation) else parse_equation(expected)
    giv = given if isinstance(given, Equation) else parse_equation(given)
    (exp_l, exp_r), (giv_l, giv_r) = exp.sides(), giv.sides()
    same_species = exp_l.keys() == giv_l.keys() and exp_r.keys() == giv_r.keys()
    same_coefficients = same_species and exp_l == giv_l and exp_r == giv_r
    multiple = None
    if same_species and not same_coefficients:
        k_left, k_right = _ratio(exp_l, giv_l), _ratio(exp_r, giv_r)
        if k_left is not None and k_left == k_right and k_left != 1:
            multiple = k_left
    return EquationCheck(same_species, same_coefficients, multiple, giv.is_balanced, giv.is_reduced)


def equation_matches(expected: str, given: str) -> bool:
    """Exact match (substances and coefficients). Unreadable input → False."""
    try:
        return compare_equations(expected, given).is_exact
    except ChemError:
        return False


# --- display ------------------------------------------------------------------

_SUB_OUT = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")
_SUP_OUT = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")


def pretty_formula(text: str, charge: int | None = None) -> str:
    """ "CuSO4·5H2O" → "CuSO₄·5H₂O", "SO4^2-" → "SO₄²⁻" (for display only)."""
    s = _normalize(text)
    if charge is None:
        try:
            s, charge = _split_charge(s)
        except ChemError:
            charge = 0
    elif "^" in s:
        s = s.partition("^")[0]
    s = re.sub(r"(?<=[A-Za-z)\]])(\d+)", lambda m: m.group(1).translate(_SUB_OUT), re.sub(r"\s+", "", s))
    s = re.sub(r"[*•∙⋅]|\.(?=\d*[A-Z(\[])", "·", s)
    if charge:
        s += (f"{abs(charge)}" if abs(charge) > 1 else "").translate(_SUP_OUT) + ("⁺" if charge > 0 else "⁻")
    return s
