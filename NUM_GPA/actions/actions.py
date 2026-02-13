from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from rasa_sdk import Action, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.interfaces import Tracker
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet, EventType


@dataclass
class GradeMap:
    letter: str
    gpa: float


def score_to_grade(score: float) -> GradeMap:
    s = float(score)
    if s >= 95:
        return GradeMap("A+", 4.0)
    if 90 <= s <= 94:
        return GradeMap("A", 3.7)
    if 87 <= s <= 89:
        return GradeMap("B+", 3.3)
    if 83 <= s <= 86:
        return GradeMap("B", 3.0)
    if 80 <= s <= 82:
        return GradeMap("B", 2.7)
    if 77 <= s <= 79:
        return GradeMap("C+", 2.3)
    if 73 <= s <= 76:
        return GradeMap("C", 2.0)
    if 70 <= s <= 72:
        return GradeMap("C", 1.7)
    if 65 <= s <= 69:
        return GradeMap("D", 1.3)
    if 60 <= s <= 64:
        return GradeMap("D", 1.0)
    if 0 <= s  <= 59:
        return GradeMap("F", 0.0)


class ValidateGpaForm(FormValidationAction):
    def name(self) -> str:
        return "validate_gpa_form"

    def validate_number_of_courses(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[str, Any]:
        try:
            n = int(float(slot_value))
        except Exception:
            dispatcher.utter_message(text="Тоогоор оруулна уу. Жишээ: 2")
            return {"number_of_courses": None}

        if not (1 <= n <= 50):
            dispatcher.utter_message(text="Хичээлийн тоо 1-50 хооронд байх ёстой.")
            return {"number_of_courses": None}

        return {"number_of_courses": n, "current_course_index": 1, "courses": []}

    def validate_current_credit(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[str, Any]:
        try:
            c = float(slot_value)
        except Exception:
            dispatcher.utter_message(text="Кредитийг тоогоор оруулна уу. Жишээ: 3")
            return {"current_credit": None}

        if not (0 < c <= 30):
            dispatcher.utter_message(text="Кредит 0-30 хооронд байх ёстой.")
            return {"current_credit": None}

        return {"current_credit": c}

    def validate_current_score(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[str, Any]:
        try:
            s = float(slot_value)
        except Exception:
            dispatcher.utter_message(text="Дүнг тоогоор оруулна уу. Жишээ: 95")
            return {"current_score": None}

        if not (0 <= s <= 100):
            dispatcher.utter_message(text="Дүн 0-100 хооронд байх ёстой.")
            return {"current_score": None}

        n = int(tracker.get_slot("number_of_courses") or 0)
        idx = int(float(tracker.get_slot("current_course_index") or 1))
        credit = float(tracker.get_slot("current_credit") or 0)

        courses = tracker.get_slot("courses") or []
        if not isinstance(courses, list):
            courses = []

        courses.append({"credit": credit, "score": s})
        next_idx = idx + 1

        # Дараагийн хичээл байгаа бол reset хийгээд үргэлжлүүлнэ
        if next_idx <= n:
            return {
                "courses": courses,
                "current_course_index": next_idx,
                "current_credit": None,
                "current_score": None,
            }

        # Сүүлчийнх — хадгалчихаад submit
        return {"courses": courses, "current_score": s}


class ActionAskCurrentCredit(Action):
    def name(self) -> str:
        return "action_ask_current_credit"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> List[EventType]:
        idx = int(float(tracker.get_slot("current_course_index") or 1))
        dispatcher.utter_message(text=f"📌 {idx}-р хичээл — кредит хэд вэ? (ж: 3кр)")
        return []


class ActionAskCurrentScore(Action):
    def name(self) -> str:
        return "action_ask_current_score"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> List[EventType]:
        idx = int(float(tracker.get_slot("current_course_index") or 1))
        dispatcher.utter_message(text=f"📝 {idx}-р хичээл — дүн хэд вэ? (0–100)")
        return []


class ActionCalculateGpa(Action):
    def name(self) -> str:
        return "action_calculate_gpa"

    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: DomainDict) -> List[EventType]:
        courses = tracker.get_slot("courses") or []
        if not courses:
            dispatcher.utter_message(text="Хичээлийн мэдээлэл алга байна. Дахин эхлүүлье.")
            return [
                SlotSet("number_of_courses", None),
                SlotSet("current_course_index", 1),
                SlotSet("current_credit", None),
                SlotSet("current_score", None),
                SlotSet("courses", []),
            ]

        total_credits = 0.0
        total_points = 0.0
        lines: List[str] = []

        for i, c in enumerate(courses, start=1):
            cr = float(c["credit"])
            sc = float(c["score"])
            g = score_to_grade(sc)

            total_credits += cr
            total_points += cr * g.gpa

            lines.append(f"{i}. {cr:g}кр - {sc:g}% → {g.letter} ({g.gpa:.1f})")

        gpa = total_points / total_credits if total_credits > 0 else 0.0

        msg = (
            "📊 Таны дүнгийн задаргаа:\n"
            + "\n".join([f"  {ln}" for ln in lines])
            + f"\n\n✅ Нийт кредит: {total_credits:g}"
            + f"\n⭐ Нийт GPA: {gpa:.2f}"
        )

        dispatcher.utter_message(text=msg)

        return [
            SlotSet("number_of_courses", None),
            SlotSet("current_course_index", 1),
            SlotSet("current_credit", None),
            SlotSet("current_score", None),
            SlotSet("courses", []),
        ]

