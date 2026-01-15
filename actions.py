from typing import Any, Dict, List, Text

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.forms import FormValidationAction
from rasa_sdk.events import SlotSet

print("✅ ACTIONS LOADED FROM:", __file__)

# ----------------------------
# CONFIG / DATA
# ----------------------------

ALLOWED_PROGRAMS = {
    "физик",
    "физик-электроник",
    "физикийн боловсрол багш",
}

ALLOWED_SEMESTERS = {str(i) for i in range(1, 9)}

COURSES: Dict[str, Dict[str, List[str]]] = {
    "физик": {
        "1": ["Математик I", "Ерөнхий физик I", "Програмчлалын үндэс", "Инженерийн график", "Англи хэл I"],
        "2": ["Математик II", "Ерөнхий физик II", "ОХП", "Электроникийн суурь", "Англи хэл II"],
        "3": ["Дифференциал тэгшитгэл", "Механик", "Цахилгаан соронзон", "Тоон арга", "Лаборатори I"],
        "4": ["Квант физикийн үндэс", "Дулаан физик", "Электроник", "Лаборатори II", "Статистик"],
        "5": ["Квант механик I", "Хатуу биеийн физик", "Оптик", "Лаборатори III", "Семинар"],
        "6": ["Квант механик II", "Цөмийн физик", "Статистик физик", "Лаборатори IV", "Төсөл I"],
        "7": ["Конденс матер", "Туршилтын арга", "Төсөл II", "Дадлага", "Сонгон"],
        "8": ["Дипломын ажил", "Мэргэжлийн дадлага", "Семинар", "Сонгон", "Хамгаалалт"],
    },
    "физик-электроник": {
        "1": ["Математик I", "Ерөнхий физик I", "Програмчлалын үндэс", "Цахилгаан хэлхээ", "Англи хэл I"],
        "2": ["Математик II", "Ерөнхий физик II", "Электроник I", "Дижитал логик", "Англи хэл II"],
        "3": ["Цахилгаан соронзон", "Аналог электроник", "Микроконтроллер", "Лаборатори I", "Сонгон"],
        "4": ["Дохиолол ба систем", "Электроник II", "Хэмжилзүй", "Embedded", "Лаборатори II"],
        "5": ["Харилцаа холбоо", "Микропроцессор", "PCB дизайн", "Лаборатори III", "Сонгон"],
        "6": ["Удирдлагын онол", "Sensors", "Загварчлал", "Лаборатори IV", "Төсөл I"],
        "7": ["IoT", "DSP", "Төсөл II", "Дадлага", "Баримтжуулалт"],
        "8": ["Дипломын төсөл", "Мэргэжлийн дадлага", "Инженерийн төсөл", "Сонгон", "Хамгаалалт"],
    },
    "физикийн боловсрол багш": {
        "1": ["Математик I", "Ерөнхий физик I", "Сурган хүмүүжүүлэх ухаан", "Сэтгэл судлал", "Англи хэл I"],
        "2": ["Математик II", "Ерөнхий физик II", "Боловсрол судлал", "Заах арга зүй", "Англи хэл II"],
        "3": ["Механик", "Цахилгаан соронзон", "Физик заах арга зүй I", "Үнэлгээ", "Лаборатори I"],
        "4": ["Дулаан физик", "Оптик", "Физик заах арга зүй II", "Хэрэглэгдэхүүн", "Лаборатори II"],
        "5": ["Орчин үеийн физик", "Сургалтын технологи", "Танхимын менежмент", "Лаборатори III", "Сонгон"],
        "6": ["Квант физикийн үндэс", "Судалгааны арга зүй", "Хичээл төлөвлөлт", "Дадлага I", "Сонгон"],
        "7": ["Дадлага II", "Үнэлгээний төсөл", "Суралцахуйн сэтгэл зүй", "Сонгон", "Бичвэр"],
        "8": ["Төгсөлтийн ажил", "Дадлага III", "Семинар", "Сонгон", "Хамгаалалт"],
    },
}


def normalize_program(text: Text) -> Text:
    return (text or "").strip().lower()


def normalize_semester(text: Text) -> Text:
    t = (text or "").strip()
    digits = "".join(ch for ch in t if ch.isdigit())
    return digits if digits else t


# ----------------------------
# FORM VALIDATION
# ----------------------------

class ValidateProgramSemesterForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_program_semester_form"

    def validate_program(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:

        # ✅ Form дахин идэвхжихэд None ирж болно: энэ үед мессеж битгий цац
        if slot_value is None:
            return {"program": None}

        program = normalize_program(str(slot_value))
        if program in ALLOWED_PROGRAMS:
            return {"program": program}

        dispatcher.utter_message(
            text="Хөтөлбөр буруу байна. Зөвхөн: физик / физик-электроник / физикийн боловсрол багш гэж бичээрэй."
        )
        return {"program": None}

    def validate_semester(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> Dict[Text, Any]:

        # ✅ None үед мессеж битгий цац
        if slot_value is None:
            return {"semester": None}

        semester = normalize_semester(str(slot_value))
        if semester in ALLOWED_SEMESTERS:
            return {"semester": semester}

        dispatcher.utter_message(text="Семестр буруу байна. 1-8 хооронд тоо оруулна уу.")
        return {"semester": None}


# ----------------------------
# ACTIONS
# ----------------------------

class ActionShowCourses(Action):
    def name(self) -> Text:
        return "action_show_courses"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        program = tracker.get_slot("program")
        semester = tracker.get_slot("semester")

        program_norm = normalize_program(program) if program else None
        semester_norm = normalize_semester(str(semester)) if semester else None

        courses = COURSES.get(program_norm, {}).get(semester_norm, [])
        if not courses:
            dispatcher.utter_message(text="Хичээлийн мэдээлэл олдсонгүй. Дахин оролдоно уу.")
            return []

        lines = "\n".join([f"- {c}" for c in courses])
        dispatcher.utter_message(text=f"{program_norm} – {semester_norm}-р семестр:\n{lines}")
        return []


class ActionResetSlots(Action):
    def name(self) -> Text:
        return "action_reset_slots"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        # ✅ Форм дахин эхлүүлэхэд хэрэгтэй slot-уудыг л цэвэрлэнэ
        return [
            SlotSet("program", None),
            SlotSet("semester", None),
            SlotSet("requested_slot", None),
        ]
