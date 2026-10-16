from .models import Question


def collect_answers(attempt, data) -> dict:
    """POST data of the quiz player → {question_id: raw answer} for submit_attempt (q<id> fields)."""
    kinds = dict(Question.objects.filter(pk__in=attempt.question_ids).values_list("pk", "kind"))
    answers = {}
    for qid in attempt.question_ids:
        name = f"q{qid}"
        answers[qid] = data.getlist(name) if kinds.get(qid) == Question.Kind.MULTIPLE else data.get(name)
    return answers
