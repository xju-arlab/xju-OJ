"""Answer cards for quiz problems: the OJ grades them itself, without a compute worker."""
import math

from .contracts import require


def answers_input(quiz, value):
    """Normalize a (possibly incomplete) answer sheet; unanswered questions become None."""
    questions = {question["id"]: question for question in quiz["questions"]}
    require(isinstance(value, dict) and not set(value) - set(questions), "作答内容无效")
    result = {}
    for qid, question in questions.items():
        answer = value.get(qid)
        count = len(question.get("options", []))
        if answer is None or answer == []:
            result[qid] = None
        elif question["kind"] == "single":
            require(type(answer) is int and 0 <= answer < count, "单选答案无效")
            result[qid] = answer
        elif question["kind"] == "multiple":
            require(isinstance(answer, list) and len(set(answer)) == len(answer) and
                    all(type(option) is int and 0 <= option < count for option in answer), "多选答案无效")
            result[qid] = sorted(answer)
        elif question["kind"] == "number":
            require(type(answer) in (int, float) and math.isfinite(answer) and abs(answer) <= 1e15, "数值答案无效")
            result[qid] = answer
        else:
            require(isinstance(answer, list) and all(type(option) is int for option in answer) and
                    sorted(answer) == list(range(count)), "排序答案无效")
            result[qid] = answer
    return result


def earned(question, key, answer):
    if answer is None:
        return 0.0
    if question["kind"] == "multiple" and key.get("scoring") == "partial":
        expected = set(key["answer"])
        hits, wrong = len(expected & set(answer)), len(set(answer) - expected)
        return question["points"] * max(0.0, (hits - wrong) / len(expected))
    if question["kind"] == "number":
        tolerance = max(key.get("tolerance", 0), key.get("relative", 0) * abs(key["answer"]))
        return float(question["points"]) if abs(answer - key["answer"]) <= tolerance + 1e-12 else 0.0
    return float(question["points"]) if answer == key["answer"] else 0.0


def grade(quiz, key, answers):
    total = sum(question["points"] for question in quiz["questions"])
    score = sum(earned(question, key[question["id"]], answers.get(question["id"])) for question in quiz["questions"])
    return round(100 * score / total, 2)
