from __future__ import annotations

from typing import Any, Dict, List, Text, Optional
from pathlib import Path

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.forms import FormValidationAction
from rasa_sdk.types import DomainDict

import yaml

import sqlite3
from datetime import datetime, timezone

DB_PATH = Path(__file__).resolve().parents[1] / "tuition.db"

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def ensure_user(conn: sqlite3.Connection, sender_id: str) -> int:
    now = utc_now_iso()
    conn.execute(
        "INSERT OR IGNORE INTO users(sender_id, created_at) VALUES(?, ?)",
        (sender_id, now),
    )
    row = conn.execute(
        "SELECT id FROM users WHERE sender_id = ?",
        (sender_id,),
    ).fetchone()
    return int(row[0])




def _load_pricing() -> dict:
    # actions/pricing.yml
    pricing_path = Path(__file__).parent / "pricing.yml"
    with pricing_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip().replace(",", ".")
        return float(s)
    except Exception:
        return None


class ValidateTuitionForm(FormValidationAction):
    def name(self) -> Text:
        return "validate_tuition_form"

    def validate_admission_group(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:

        intent = tracker.latest_message.get("intent", {}).get("name")

        intent_to_group = {
            "choose_admission_before_2024_2025": "before_2024_2025",
            "choose_admission_2024_2025": "2024_2025",
            "choose_admission_2025_2026": "2025_2026",
        }

        if intent in intent_to_group:
            return {"admission_group": intent_to_group[intent]}

        # fallback: text-ээр шууд бичсэн тохиолдолд
        allowed = {"before_2024_2025", "2024_2025", "2025_2026"}
        if slot_value in allowed:
            return {"admission_group": slot_value}

        dispatcher.utter_message(text="Сонголтоо товч дээр дарж сонгоорой.")
        return {"admission_group": None}


    def validate_faculty(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        pricing = _load_pricing()
        group = tracker.get_slot("admission_group")
        if not group or group not in pricing:
            dispatcher.utter_message(text="Эхлээд элсэлтийн оноо сонгоорой.")
            return {"faculty": None}

        faculties = set(pricing[group].keys())
        if slot_value in faculties:
            return {"faculty": slot_value}

        dispatcher.utter_message(text="Бүрэлдэхүүн/салбараа товч дээр дарж сонгоорой.")
        return {"faculty": None}

    def validate_general_credits(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        v = _to_float(slot_value)
        if v is None or v < 0:
            dispatcher.utter_message(text="Ерөнхий суурь кредитийг 0-ээс их эсвэл тэнцүү тоогоор оруулна уу.")
            return {"general_credits": None}
        return {"general_credits": v}

    def validate_major_credits(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        v = _to_float(slot_value)
        if v is None or v < 0:
            dispatcher.utter_message(text="Мэргэжлийн суурь/мэргэших кредитийг 0-ээс их эсвэл тэнцүү тоогоор оруулна уу.")
            return {"major_credits": None}
        return {"major_credits": v}


class ActionCalculateTuition(Action):
    def name(self) -> Text:
        return "action_calculate_tuition"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        pricing = _load_pricing()

        group = tracker.get_slot("admission_group")
        faculty = tracker.get_slot("faculty")
        gen_cr = _to_float(tracker.get_slot("general_credits")) or 0.0
        maj_cr = _to_float(tracker.get_slot("major_credits")) or 0.0

        if not group or not faculty:
            dispatcher.utter_message(text="Мэдээлэл дутуу байна. Дахиад 'төлбөр бодоорой' гэж эхлүүлнэ үү.")
            return []

        try:
            rates = pricing[group][faculty]
            gen_rate = float(rates["general"])
            maj_rate = float(rates["major"])
        except Exception:
            dispatcher.utter_message(text="Уучлаарай, сонгосон өгөгдлийн үнэ хүснэгтээс олдсонгүй.")
            return []

        total = gen_cr * gen_rate + maj_cr * maj_rate
                # --- SAVE TO DB ---
        sender_id = tracker.sender_id
        try:
            with get_conn() as conn:
                user_id = ensure_user(conn, sender_id)
                conn.execute(
                    """
                    INSERT INTO tuition_runs(
                        user_id, admission_group, faculty,
                        general_credits, major_credits,
                        general_rate, major_rate,
                        total_tuition, created_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        user_id,
                        str(group),
                        str(faculty),
                        float(gen_cr),
                        float(maj_cr),
                        float(gen_rate),
                        float(maj_rate),
                        float(total),
                        utc_now_iso(),
                    ),
                )
                conn.commit()
        except Exception as e:
            dispatcher.utter_message(text=f"(DB хадгалалт амжилтгүй: {e})")


        def fmt(n: float) -> str:
            return f"{int(round(n)):,}".replace(",", ",")

        msg = (
            f"Таны сонголт:\n"
            f"- Элсэлт: {group}\n"
            f"- Бүрэлдэхүүн/салбар: {faculty}\n\n"
            f"Тооцоолол:\n"
            f"- Ерөнхий суурь: {gen_cr} кр × {fmt(gen_rate)} ₮ = {fmt(gen_cr * gen_rate)} ₮\n"
            f"- Мэргэжлийн суурь/мэргэших: {maj_cr} кр × {fmt(maj_rate)} ₮ = {fmt(maj_cr * maj_rate)} ₮\n\n"
            f"✅ Нийт төлөх төлбөр: {fmt(total)} ₮"
        )

        dispatcher.utter_message(text=msg)
        return []
from rasa_sdk.events import SlotSet

class ActionSetAdmissionBefore(Action):
    def name(self) -> Text:
        return "action_set_admission_group_before_2024_2025"

    def run(self, dispatcher, tracker, domain):
        return [SlotSet("admission_group", "before_2024_2025")]

class ActionSetAdmission2024(Action):
    def name(self) -> Text:
        return "action_set_admission_group_2024_2025"

    def run(self, dispatcher, tracker, domain):
        return [SlotSet("admission_group", "2024_2025")]

class ActionSetAdmission2025(Action):
    def name(self) -> Text:
        return "action_set_admission_group_2025_2026"

    def run(self, dispatcher, tracker, domain):
        return [SlotSet("admission_group", "2025_2026")]

class ActionSetFacultyScience(Action):
    def name(self) -> Text:
        return "action_set_faculty_science"
    def run(self, dispatcher, tracker, domain):
        return [SlotSet("faculty", "ШИНЖЛЭХ УХААНЫ СУРГУУЛЬ")]

class ActionSetFacultyMTEE(Action):
    def name(self) -> Text:
        return "action_set_faculty_mtee"
    def run(self, dispatcher, tracker, domain):
        return [SlotSet("faculty", "МЭДЭЭЛЛИЙН ТЕХНОЛОГИ, ЭЛЕКТРОНИКИЙН СУРГУУЛЬ")]

class ActionSetFacultyEngineering(Action):
    def name(self) -> Text:
        return "action_set_faculty_engineering"
    def run(self, dispatcher, tracker, domain):
        return [SlotSet("faculty", "ИНЖЕНЕР, ТЕХНОЛОГИЙН СУРГУУЛЬ")]

class ActionSetFacultyBusiness(Action):
    def name(self) -> Text:
        return "action_set_faculty_business"
    def run(self, dispatcher, tracker, domain):
        return [SlotSet("faculty", "БИЗНЕСИЙН СУРГУУЛЬ")]

class ActionSetFacultyLaw(Action):
    def name(self) -> Text:
        return "action_set_faculty_law"
    def run(self, dispatcher, tracker, domain):
        return [SlotSet("faculty", "ХУУЛЬ ЗҮЙН СУРГУУЛЬ")]

class ActionSetFacultyPolitics(Action):
    def name(self) -> Text:
        return "action_set_faculty_politics"
    def run(self, dispatcher, tracker, domain):
        return [SlotSet("faculty", "УЛС ТӨР СУДЛАЛ, ОЛОН УЛСЫН ХАРИЛЦАА, НИЙТИЙН УДИРДЛАГЫН СУРГУУЛЬ")]

class ActionSetFacultyZavkhan(Action):
    def name(self) -> Text:
        return "action_set_faculty_zavkhan"
    def run(self, dispatcher, tracker, domain):
        return [SlotSet("faculty", "ЗАВХАН АЙМАГ ДАХЬ БИЗНЕС, МЭДЭЭЛЛИЙН ТЕХНОЛОГИЙН СУРГУУЛЬ")]

class ActionSetFacultyEast(Action):
    def name(self) -> Text:
        return "action_set_faculty_east"
    def run(self, dispatcher, tracker, domain):
        return [SlotSet("faculty", "ЗҮҮН БҮСИЙН СУРГУУЛЬ")]

class ActionSetFacultyWest(Action):
    def name(self) -> Text:
        return "action_set_faculty_west"
    def run(self, dispatcher, tracker, domain):
        return [SlotSet("faculty", "БАРУУН БҮСИЙН СУРГУУЛЬ")]

