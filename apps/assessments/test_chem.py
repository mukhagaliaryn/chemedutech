"""Unit tests of apps.assessments.chem (no database)."""

from fractions import Fraction

from django.test import SimpleTestCase, TestCase

from .chem import (
    ChemError,
    compare_equations,
    equation_matches,
    formulas_equal,
    parse_equation,
    parse_formula,
    pretty_formula,
)
from .models import Question, Quiz
from .services import grade

# Every equation of topic 1 (theory, lab and tests) — all must parse and balance.
TOPIC_1_EQUATIONS = [
    "Zn + 2HCl -> ZnCl2 + H2",
    "Zn + H2SO4 -> ZnSO4 + H2",
    "Fe + 2HCl -> FeCl2 + H2",
    "2H2 + O2 -> 2H2O",
    "2H2O2 -> 2H2O + O2",
    "2H2O -> 2H2 + O2",
    "2KMnO4 -> K2MnO4 + MnO2 + O2",
    "2KClO3 -> 2KCl + 3O2",
    "Zn + 2H+ -> Zn2+ + H2",
    "CuO + H2 -> Cu + H2O",
]


class FormulaParsingTests(SimpleTestCase):
    def counts(self, text):
        return parse_formula(text).counts

    def test_simple(self):
        self.assertEqual(self.counts("H2O"), {"H": 2, "O": 1})

    def test_two_letter_elements(self):
        self.assertEqual(self.counts("ZnCl2"), {"Zn": 1, "Cl": 2})

    def test_parentheses(self):
        self.assertEqual(self.counts("Ca(OH)2"), {"Ca": 1, "O": 2, "H": 2})

    def test_nested_and_square_brackets(self):
        self.assertEqual(self.counts("K3[Fe(CN)6]"), {"K": 3, "Fe": 1, "C": 6, "N": 6})

    def test_parentheses_multiplier(self):
        self.assertEqual(self.counts("Al2(SO4)3"), {"Al": 2, "S": 3, "O": 12})

    def test_hydrate_middle_dot(self):
        self.assertEqual(self.counts("CuSO4·5H2O"), {"Cu": 1, "S": 1, "O": 9, "H": 10})

    def test_hydrate_typed_variants(self):
        for text in ("CuSO4.5H2O", "CuSO4*5H2O", "CuSO4 · 5H2O", "CuSO4•5H2O"):
            with self.subTest(text):
                self.assertEqual(self.counts(text), {"Cu": 1, "S": 1, "O": 9, "H": 10})

    def test_unicode_subscripts(self):
        self.assertEqual(parse_formula("H₂O₂").key, parse_formula("H2O2").key)

    def test_spaces_are_ignored(self):
        self.assertEqual(self.counts(" Zn Cl 2 "), {"Zn": 1, "Cl": 2})

    def test_repeated_element_is_summed(self):
        self.assertEqual(self.counts("CH3COOH"), {"C": 2, "H": 4, "O": 2})

    def test_case_matters(self):
        self.assertEqual(self.counts("Co"), {"Co": 1})
        self.assertEqual(self.counts("CO"), {"C": 1, "O": 1})

    def test_monatomic_ions(self):
        for text, charge in (("Zn2+", 2), ("Fe3+", 3), ("Cl-", -1), ("Na+", 1), ("Fe+++", 3)):
            with self.subTest(text):
                self.assertEqual(parse_formula(text).charge, charge)

    def test_polyatomic_ions_single_digit_is_a_count(self):
        self.assertEqual(parse_formula("NH4+").key, ((("H", 4), ("N", 1)), 1))
        self.assertEqual(parse_formula("H3O+").charge, 1)
        self.assertEqual(parse_formula("NO3-").counts, {"N": 1, "O": 3})

    def test_charge_notations_are_equivalent(self):
        keys = {parse_formula(t).key for t in ("SO4^2-", "SO42-", "SO₄²⁻", "SO4 2-", "SO4^-2")}
        self.assertEqual(keys, {((("O", 4), ("S", 1)), -2)})

    def test_complex_ion_charge_after_bracket(self):
        self.assertEqual(parse_formula("[Fe(CN)6]4-").charge, -4)
        self.assertEqual(parse_formula("[Cu(NH3)4]2+").counts["H"], 12)

    def test_caret_disambiguates(self):
        self.assertEqual(parse_formula("O2^-").key, ((("O", 2),), -1))
        self.assertEqual(parse_formula("O^2-").key, ((("O", 1),), -2))

    def test_errors(self):
        cases = {
            "": "empty",
            "co": "lowercase_element",
            "Xx2": "unknown_element",
            "Ca(OH2": "unbalanced_brackets",
            "H2O)": "unbalanced_brackets",
            "Ca()2": "empty_brackets",
            "2H2O": "leading_coefficient",
            "H0": "zero_count",
            "H2$O": "unexpected_symbol",  # two pieces of chemistry: nothing is guessed
            "Fe3++": "bad_charge",
        }
        for text, code in cases.items():
            with self.subTest(text):
                with self.assertRaises(ChemError) as ctx:
                    parse_formula(text)
                self.assertEqual(ctx.exception.code, code)

    def test_formulas_equal_ignores_writing_order(self):
        self.assertTrue(formulas_equal("ZnCl2", "Cl2Zn"))
        self.assertTrue(formulas_equal("ZnCl2", "ZnCl₂"))

    def test_formulas_equal_rejects_wrong_counts_and_charge(self):
        self.assertFalse(formulas_equal("ZnCl2", "ZnCl"))
        self.assertFalse(formulas_equal("Zn2+", "Zn"))
        self.assertFalse(formulas_equal("H2O", "h2o"))
        self.assertFalse(formulas_equal("H2O", ""))

    def test_words_around_the_answer_are_ignored(self):
        cases = {
            "Zn + 2HCl -> ZnCl2 + H2. дұрыс жауабы осы": "Zn + 2HCl -> ZnCl2 + H2",
            "Жауабы: Zn + 2HCl = ZnCl2 + H2↑": "Zn + 2HCl -> ZnCl2 + H2",
            "«Zn + 2HCl → ZnCl₂ + H₂»": "Zn + 2HCl -> ZnCl2 + H2",
            "2H2O2 →(MnO2) 2H2O + O2 (катализатор)": "2H2O2 -> 2H2O + O2",
            "Ag⁺ + Cl⁻ → AgCl↓ (ақ тұнба)": "Ag+ + Cl- -> AgCl",
            "Жауап: NH4+ + OH- -> NH3 + H2O, аммиак бөлінеді": "NH4+ + OH- -> NH3 + H2O",
        }
        for text, expected in cases.items():
            with self.subTest(text):
                self.assertTrue(compare_equations(expected, text).same_coefficients)
        self.assertEqual(parse_formula("ZnCl2 — мырыш хлориді").key, parse_formula("ZnCl2").key)
        self.assertEqual(parse_formula("Жауабы: ZnCl₂.").key, parse_formula("ZnCl2").key)
        with self.assertRaises(ChemError):
            parse_equation("мырыш + тұз қышқылы")  # words only: still no equation

    def test_pretty(self):
        self.assertEqual(pretty_formula("CuSO4.5H2O"), "CuSO₄·5H₂O")
        self.assertEqual(pretty_formula("SO4^2-"), "SO₄²⁻")
        self.assertEqual(parse_formula("NH4+").pretty(), "NH₄⁺")
        self.assertEqual(parse_formula("Ca(OH)2").pretty(), "Ca(OH)₂")


class EquationParsingTests(SimpleTestCase):
    def test_topic_1_equations_balance(self):
        for text in TOPIC_1_EQUATIONS:
            with self.subTest(text):
                eq = parse_equation(text)
                self.assertTrue(eq.is_balanced)
                self.assertTrue(eq.is_reduced)

    def test_arrow_variants(self):
        base = parse_equation("2H2 + O2 -> 2H2O").sides()
        for arrow in ("=", "→", "⟶", "=>", "⇌", "<=>", "<->"):
            with self.subTest(arrow):
                self.assertEqual(parse_equation(f"2H2 + O2 {arrow} 2H2O").sides(), base)

    def test_reversible_flag(self):
        self.assertTrue(parse_equation("N2 + 3H2 ⇌ 2NH3").reversible)
        self.assertFalse(parse_equation("N2 + 3H2 -> 2NH3").reversible)

    def test_gas_and_precipitate_marks_are_ignored(self):
        self.assertEqual(
            parse_equation("Zn + 2HCl → ZnCl2 + H2↑").sides(), parse_equation("Zn + 2HCl -> ZnCl2 + H2").sides()
        )
        self.assertTrue(parse_equation("BaCl2 + Na2SO4 -> BaSO4↓ + 2NaCl").is_balanced)

    def test_state_symbols_are_ignored(self):
        self.assertTrue(parse_equation("Zn(s) + 2HCl(aq) -> ZnCl2(aq) + H2(g)").is_balanced)

    def test_no_spaces(self):
        self.assertTrue(parse_equation("Zn+2HCl=ZnCl2+H2").is_balanced)

    def test_catalyst_next_to_the_arrow(self):
        for text in ("2H2O2 →(MnO2) 2H2O + O2", "2H2O2 → 2H2O + O2 (MnO2)", "2KMnO4 →t° K2MnO4 + MnO2 + O2"):
            with self.subTest(text):
                self.assertTrue(parse_equation(text).is_balanced)

    def test_ionic_equation_with_spaced_pluses(self):
        eq = parse_equation("Zn + 2H+ → Zn2+ + H2")
        self.assertEqual([t.formula.charge for t in eq.products], [2, 0])
        self.assertTrue(eq.charge_balanced)

    def test_ionic_equation_without_spaces(self):
        eq = parse_equation("Ba2++SO42-=BaSO4")
        self.assertEqual([t.formula.charge for t in eq.reactants], [2, -2])
        self.assertTrue(eq.is_balanced)

    def test_unbalanced_atoms(self):
        eq = parse_equation("Zn + HCl -> ZnCl2 + H2")
        self.assertFalse(eq.atoms_balanced)
        self.assertFalse(eq.is_balanced)

    def test_unbalanced_charge(self):
        eq = parse_equation("Fe3+ + Zn -> Fe2+ + Zn2+")
        self.assertTrue(eq.atoms_balanced)
        self.assertFalse(eq.charge_balanced)

    def test_coefficients_parsed(self):
        eq = parse_equation("2KClO3 -> 2KCl + 3O2")
        self.assertEqual([t.coefficient for t in eq.products], [2, 3])

    def test_hydrate_in_equation(self):
        self.assertTrue(parse_equation("CuSO4·5H2O -> CuSO4 + 5H2O").is_balanced)

    def test_errors(self):
        cases = {
            "Zn + 2HCl ZnCl2 + H2": "no_arrow",
            "A -> B -> C": "many_arrows",
            "-> H2O": "empty_side",
            "H2 + -> H2": "empty_term",
            "0H2 + O2 -> H2O": "zero_coefficient",
            "zn + 2HCl -> ZnCl2 + H2": "lowercase_element",
            "Zn + 2Hcl -> ZnCl2 + H2": "unknown_element",  # "Hc"
        }
        for text, code in cases.items():
            with self.subTest(text):
                with self.assertRaises(ChemError) as ctx:
                    parse_equation(text)
                self.assertEqual(ctx.exception.code, code)

    def test_pretty(self):
        self.assertEqual(parse_equation("2H2O2 -> 2H2O + O2").pretty(), "2H₂O₂ → 2H₂O + O₂")
        self.assertEqual(parse_equation("Zn + 2H+ = Zn2+ + H2").pretty(), "Zn + 2H⁺ → Zn²⁺ + H₂")


class EquationComparisonTests(SimpleTestCase):
    def test_exact_match(self):
        check = compare_equations("Zn + 2HCl -> ZnCl2 + H2", "Zn + 2HCl = ZnCl2 + H2↑")
        self.assertTrue(check.is_exact)

    def test_order_of_substances_does_not_matter(self):
        self.assertTrue(equation_matches("2H2 + O2 -> 2H2O", "O2 + 2H2 → 2H2O"))
        self.assertTrue(equation_matches("2KMnO4 -> K2MnO4 + MnO2 + O2", "2KMnO4 = O2 + MnO2 + K2MnO4"))

    def test_multiplied_coefficients_flagged(self):
        check = compare_equations("2H2 + O2 -> 2H2O", "4H2 + 2O2 → 4H2O")
        self.assertFalse(check.is_exact)
        self.assertEqual(check.multiple, Fraction(2))
        self.assertTrue(check.balanced)
        self.assertTrue(check.balanced_not_reduced)

    def test_missing_coefficients(self):
        check = compare_equations("2H2O2 -> 2H2O + O2", "H2O2 -> H2O + O2")
        self.assertTrue(check.same_species)
        self.assertFalse(check.same_coefficients)
        self.assertFalse(check.balanced)
        self.assertIsNone(check.multiple)
        self.assertFalse(check.balanced_not_reduced)

    def test_wrong_product(self):
        check = compare_equations("Zn + 2HCl -> ZnCl2 + H2", "Zn + 2HCl -> ZnCl + H2")
        self.assertFalse(check.same_species)

    def test_swapped_sides_are_wrong(self):
        self.assertFalse(compare_equations("2H2 + O2 -> 2H2O", "2H2O -> 2H2 + O2").same_species)

    def test_split_terms_are_merged(self):
        self.assertTrue(equation_matches("2H2 + O2 -> 2H2O", "H2 + H2 + O2 -> 2H2O"))

    def test_formula_written_differently(self):
        self.assertTrue(equation_matches("Ca + 2H2O -> Ca(OH)2 + H2", "Ca + 2H2O -> CaO2H2 + H2"))

    def test_unreadable_answer_does_not_match(self):
        self.assertFalse(equation_matches("2H2 + O2 -> 2H2O", "сутегі + оттегі = су"))
        self.assertFalse(equation_matches("2H2 + O2 -> 2H2O", ""))

    def test_extra_substance(self):
        self.assertFalse(equation_matches("2H2 + O2 -> 2H2O", "2H2 + O2 + N2 -> 2H2O + N2"))


class QuizChemGradingTests(TestCase):
    def setUp(self):
        self.quiz = Quiz.objects.create(title="Chem")

    def test_formula_question(self):
        q = Question.objects.create(quiz=self.quiz, kind="formula", text="t", accepted_answers=["ZnCl2"])
        self.assertTrue(grade(q, "ZnCl₂").is_correct)
        self.assertTrue(grade(q, " Zn Cl2 ").is_correct)
        self.assertFalse(grade(q, "ZnCl").is_correct)
        self.assertFalse(grade(q, "zncl2").is_correct)
        self.assertEqual(grade(q, "ZnCl₂").text_value, "ZnCl₂")  # stored as typed

    def test_equation_question(self):
        q = Question.objects.create(quiz=self.quiz, kind="equation", text="t", accepted_answers=["2H2O2 -> 2H2O + O2"])
        self.assertTrue(grade(q, "2H₂O₂ = O₂↑ + 2H₂O").is_correct)
        self.assertFalse(grade(q, "4H2O2 -> 4H2O + 2O2").is_correct)
        self.assertFalse(grade(q, "H2O2 -> H2O + O2").is_correct)
        self.assertFalse(grade(q, "not an equation").is_correct)

    def test_question_validation(self):
        from django.core.exceptions import ValidationError

        bad = [
            ("formula", ["Xx"]),
            ("formula", []),
            ("equation", ["H2 + O2 -> H2O"]),  # not balanced
            ("equation", ["H2O"]),  # no arrow
        ]
        for kind, answers in bad:
            with self.subTest(kind=kind, answers=answers):
                with self.assertRaises(ValidationError):
                    Question(quiz=self.quiz, kind=kind, text="t", accepted_answers=answers).full_clean()
        Question(quiz=self.quiz, kind="equation", text="t", accepted_answers=["2H2 + O2 -> 2H2O"]).full_clean()
