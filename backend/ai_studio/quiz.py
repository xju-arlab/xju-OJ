"""Answer cards for quiz problems: the OJ grades them itself, without a compute worker.

Objective questions are graded on submission; free-text questions are scored by a teacher.
"""
import math

from .contracts import require
from .package_format import MAX_TEXT_ANSWER


def answers_input(quiz, value):
    """Normalize a (possibly incomplete) answer sheet; unanswered questions become None."""
    questions = {question["id"]: question for question in quiz["questions"]}
    require(isinstance(value, dict) and not set(value) - set(questions), "作答内容无效")
    result = {}
    for qid, question in questions.items():
        answer = value.get(qid)
        count = len(question.get("options", []))
        if question["kind"] == "text":
            require(answer is None or (isinstance(answer, str) and len(answer) <= MAX_TEXT_ANSWER and "\x00" not in answer),
                    f"主观题作答不能超过 {MAX_TEXT_ANSWER} 字")
            result[qid] = answer if answer and answer.strip() else None
        elif answer is None or answer == []:
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
    if answer is None or question["kind"] == "text":
        return 0.0
    if question["kind"] == "multiple" and key.get("scoring") == "partial":
        expected = set(key["answer"])
        hits, wrong = len(expected & set(answer)), len(set(answer) - expected)
        return question["points"] * max(0.0, (hits - wrong) / len(expected))
    if question["kind"] == "number":
        tolerance = max(key.get("tolerance", 0), key.get("relative", 0) * abs(key["answer"]))
        return float(question["points"]) if abs(answer - key["answer"]) <= tolerance + 1e-12 else 0.0
    return float(question["points"]) if answer == key["answer"] else 0.0


def text_questions(quiz):
    return [question for question in quiz["questions"] if question["kind"] == "text"]


def grade(quiz, key, answers, manual=None):
    """Percentage score; `manual` maps free-text question ids to the teacher's points."""
    total = sum(question["points"] for question in quiz["questions"])
    score = sum(earned(question, key[question["id"]], answers.get(question["id"])) for question in quiz["questions"])
    score += sum((manual or {}).get(question["id"], 0) for question in text_questions(quiz))
    return round(100 * score / total, 2)


def review_ceiling(quiz, key, answers):
    """Best reachable percentage if every answered free-text question got full marks."""
    best = {question["id"]: question["points"] for question in text_questions(quiz) if answers.get(question["id"])}
    return grade(quiz, key, answers, best)


def manual_input(quiz, answers, value):
    """Validate a teacher's points for the answered free-text questions; unanswered ones score 0."""
    expected = {question["id"]: question for question in text_questions(quiz) if answers.get(question["id"])}
    require(isinstance(value, dict) and set(value) == set(expected), "请为每道已作答的主观题给分")
    for qid, points in value.items():
        require(type(points) in (int, float) and math.isfinite(points) and 0 <= points <= expected[qid]["points"],
                f"主观题得分必须在 0–{expected[qid]['points']} 之间")
    return {qid: float(points) for qid, points in value.items()}
