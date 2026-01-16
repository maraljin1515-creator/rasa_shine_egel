from typing import Any, Dict, List, Optional, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.forms import FormValidationAction
from rasa_sdk.types import DomainDict
from rasa_sdk.events import SlotSet, ActiveLoop


def _to_float(text: Any) -> Optional[float]:
    if text is None:
        return None
    s = str(text).strip()
    # "3 кредит" "95%" гэх мэтээс тоо түүх
    buf = "".join(ch if (ch.isdigit() or ch == ".") else " " for ch in s)
    parts = buf.split()
    if not parts:
        return None
    try:
        return float(parts[0])
    except Exception:
        return None


def _score_to_letter_point(score: float):
    # Жишээ шкал (та өөрийн сургуулийнхaaар солино)
    if score >= 95:
        return "A+", 4.0
    if score >= 90:
        return "A", 4.0
    if score >= 85:
        return "A-", 3.7
    if score >= 80:
        return "B+", 3.3
    if score >= 75:
        return "B", 3.0
    if score >= 70:
        return "B-", 2.7
    if score >= 65:
        return "C+", 2.3
    if score >= 60:
        return "C", 2.0
    if score >= 55:
        return "C-", 1.7
    if score >= 50:
        return "D", 1.0
    return "F", 0.0


class ValidateGpaForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_gpa_form"

    async def validate_number_of_courses(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        n = _to_float(slot_value)
        if n is None:
            dispatcher.utter_message(text="Хичээлийн тоо буруу байна. Жишээ: 2, 3, 4 гэж бичээрэй.")
            return {"number_of_courses": None}

        n = int(n)
        if n <= 0 or n > 30:
            dispatcher.utter_message(text="Хичээлийн тоо 1-30 хооронд байна.")
            return {"number_of_courses": None}

        # эхлэх үед индекс, courses reset
        return {"number_of_courses": float(n), "current_course_index": 1.0, "courses": []}

    async def validate_current_credit(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        c = _to_float(slot_value)
        if c is None:
            dispatcher.utter_message(text="Кредит буруу байна. Жишээ: 3, 4 гэж бичээрэй.")
            return {"current_credit": None}

        c = float(c)
        if c <= 0 or c > 20:
            dispatcher.utter_message(text="Кредит 1-20 хооронд байна.")
            return {"current_credit": None}

        return {"current_credit": c}

    async def validate_current_score(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        s = _to_float(slot_value)
        if s is None:
            dispatcher.utter_message(text="Дүн буруу байна. 0-100 хооронд тоо оруулаарай.")
            return {"current_score": None}

        s = float(s)
        if s < 0 or s > 100:
            dispatcher.utter_message(text="Дүн 0-100 хооронд байна.")
            return {"current_score": None}

        n = int(float(tracker.get_slot("number_of_courses") or 0))
        idx = int(float(tracker.get_slot("current_course_index") or 1))
        credit = float(tracker.get_slot("current_credit") or 0.0)

        # хамгаалалт: нэг idx-г давхар нэмэхгүй
        courses: List[Dict[str, Any]] = tracker.get_slot("courses") or []
        if any(int(c.get("index", -1)) == idx for c in courses):
            return {"current_score": None}

        letter, point = _score_to_letter_point(s)
        courses.append(
            {"index": idx, "credit": credit, "score": s, "letter": letter, "point": point}
        )

        # ✅ ДАВТАЛТ ДУУСАХ НӨХЦӨЛ
        if idx >= n:
            # form дуусахын тулд required_slots дахин асуухгүй болгож,
            # submit rule ажиллах нөхцөл бүрдүүлнэ.
            return {
                "courses": courses,
                "current_score": None,
                "current_credit": None,
                "requested_slot": None,
            }

        # дараагийн хичээл рүү шилжинэ
        return {
            "courses": courses,
            "current_course_index": float(idx + 1),
            "current_score": None,
            "current_credit": None,
        }


class ActionGpaResult(Action):
    def name(self) -> Text:
        return "action_gpa_result"

    async def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> List[Dict[Text, Any]]:
        courses = tracker.get_slot("courses") or []
        total_credits = sum(float(c["credit"]) for c in courses)
        total_points = sum(float(c["credit"]) * float(c["point"]) for c in courses)
        gpa = (total_points / total_credits) if total_credits > 0 else 0.0

        lines = ["Таны дүнгийн задаргаа:"]
        for c in courses:
            lines.append(
                f"  {int(c['index'])}. {int(c['credit'])}кр - {int(c['score'])}% → {c['letter']} ({c['point']:.1f})"
            )
        lines.append(f"Нийт кредит: {int(total_credits)}")
        lines.append(f"Нийт GPA: {gpa:.2f}")

        dispatcher.utter_message(text="\n".join(lines))
        # шинэ тооцоонд бэлэн болгоод цэвэрлэж болно
        return [SlotSet("current_course_index", None), SlotSet("courses", None)]
