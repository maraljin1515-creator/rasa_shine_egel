from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

# -----------------------------
# Helpers
# -----------------------------

NUM_ONLY_RE = re.compile(r"^\s*(\d{1,2})\s*$")
BAIR_RE = re.compile(r"^\s*(\d{1,2})\s*[-‐-–—]?\s*р?\s*байр\s*$", re.IGNORECASE)
BAIR_LOOSE_RE = re.compile(r"(\d{1,2})\s*[-‐-–—]?\s*р?\s*бай[аa]р", re.IGNORECASE)

# Safety filters (per your requirement)
FORBIDDEN = {
    ("dorm", 4),   # no dorm 4
    ("class", 6),  # no class building 6
}

def norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("ё", "е")
    s = re.sub(r"[“”\"'`]", "", s)
    s = re.sub(r"[,\.\(\)\[\]\{\}]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def detect_kind(text: str) -> Optional[str]:
    t = norm(text)
    if "дотуур" in t or "dorm" in t:
        return "dorm"
    if "хичээл" in t or "хичээлийн" in t or "сургуулийн" in t or "academic" in t:
        return "class"
    return None

def extract_number(text: str) -> Optional[int]:
    t = text.strip()
    m = NUM_ONLY_RE.match(t)
    if m:
        return int(m.group(1))
    m = BAIR_RE.match(t)
    if m:
        return int(m.group(1))
    m = BAIR_LOOSE_RE.search(t)
    if m:
        return int(m.group(1))
    return None

def is_list_request(text: str) -> bool:
    t = norm(text)
    return t in {"байршлууд", "жагсаалт", "locations", "list", "байршилууд"}

# -----------------------------
# Load locations.yml
# -----------------------------

def load_places() -> Tuple[Dict[str, Dict[str, Any]], Dict[Tuple[str, int], Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Returns:
      alias_index: normalized alias -> place
      kind_num_index: (kind, number) -> place
      all_places: list of place dicts (filtered)
    """
    path = Path("locations.yml")
    if not path.exists():
        alt = Path(__file__).resolve().parent / "locations.yml"
        if alt.exists():
            path = alt

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw_places: List[Dict[str, Any]] = data.get("places", []) if isinstance(data, dict) else []

    # ✅ filter forbidden entries even if someone accidentally adds them back
    places: List[Dict[str, Any]] = []
    for p in raw_places:
        if not isinstance(p, dict):
            continue
        kind = str(p.get("kind") or "")
        num = p.get("number")
        if isinstance(num, int) and (kind, num) in FORBIDDEN:
            continue
        places.append(p)

    alias_index: Dict[str, Dict[str, Any]] = {}
    kind_num_index: Dict[Tuple[str, int], Dict[str, Any]] = {}

    for p in places:
        aliases = p.get("aliases", []) or []
        for a in aliases:
            alias_index[norm(str(a))] = p
        kind = p.get("kind")
        num = p.get("number")
        if kind and isinstance(num, int):
            kind_num_index[(str(kind), num)] = p

    return alias_index, kind_num_index, places

_ALIAS_INDEX, _KIND_NUM_INDEX, _ALL_PLACES = load_places()

def say_place(dispatcher: CollectingDispatcher, place: Dict[str, Any]) -> None:
    title = place.get("title", "Байршил")
    url = (place.get("url") or "").strip()
    if url:
        dispatcher.utter_message(f"{title}\n{url}")
    else:
        dispatcher.utter_message(
            f"{title}\n(⚠️ Google Maps линк одоогоор locations.yml дээр байхгүй байна — линкээ нэмээд дахин туршаарай.)"
        )

# -----------------------------
# Action
# -----------------------------

class ActionSendLocation(Action):
    def name(self) -> str:
        return "action_send_location"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        text = (tracker.latest_message.get("text") or "").strip()
        latest_intent = (tracker.latest_message.get("intent") or {}).get("name")

        pending_number = tracker.get_slot("pending_number")
        place_type = tracker.get_slot("place_type")

        # 1) If user is answering the clarification question
        if latest_intent == "choose_place_type" and pending_number:
            chosen_kind = detect_kind(text) or (place_type if place_type in {"class", "dorm"} else None)
            if chosen_kind is None:
                dispatcher.utter_message("“хичээлийн байр” эсвэл “дотуур байр” гэж хариулаарай 🙂")
                return []

            try:
                num = int(str(pending_number))
            except Exception:
                num = None

            if num is not None:
                # safety: block forbidden
                if (chosen_kind, num) in FORBIDDEN:
                    dispatcher.utter_message("Уучлаарай, тэр байрны мэдээлэл энэ бот дээр байхгүй байна.")
                    return [SlotSet("pending_number", None), SlotSet("place_type", chosen_kind)]

                place = _KIND_NUM_INDEX.get((chosen_kind, num))
                if place:
                    say_place(dispatcher, place)
                    return [SlotSet("pending_number", None), SlotSet("place_type", chosen_kind)]

            dispatcher.utter_message("Уучлаарай, тэр дугаартай байршил олдсонгүй. Дахиад нэрээр нь бичээд үзээрэй.")
            return [SlotSet("pending_number", None)]

        # 2) List request
        if is_list_request(text):
            lines = ["Боломжтой байршлууд:"]
            for p in _ALL_PLACES:
                title = p.get("title")
                if title:
                    lines.append(f"• {title}")
            dispatcher.utter_message("\n".join(lines))
            return []

        # 3) Determine kind + number + ambiguity
        kind = detect_kind(text)
        num = extract_number(text)

        # If user wrote only "1", "2", or "2-р байр" without specifying kind -> ask
        if num is not None and kind is None and (NUM_ONLY_RE.match(text) or BAIR_RE.match(text) or BAIR_LOOSE_RE.search(text)):
            dispatcher.utter_message(response="utter_ask_place_type")
            return [SlotSet("pending_number", str(num))]

        # 4) If kind+num is present, use index
        if num is not None and kind in {"class", "dorm"}:
            if (kind, num) in FORBIDDEN:
                dispatcher.utter_message("Уучлаарай, тэр байрны мэдээлэл энэ бот дээр байхгүй байна.")
                return [SlotSet("place_type", kind), SlotSet("pending_number", None)]

            place = _KIND_NUM_INDEX.get((kind, num))
            if place:
                say_place(dispatcher, place)
                return [SlotSet("place_type", kind), SlotSet("pending_number", None)]

            dispatcher.utter_message("Уучлаарай, тэр дугаартай байршил олдсонгүй. Дахиад нэрээр нь бичээд үзээрэй.")
            return []

        # 5) Try to match by alias
        ntext = norm(text)

        # a) exact alias
        place = _ALIAS_INDEX.get(ntext)
        if place:
            say_place(dispatcher, place)
            return []

        # b) contains match (best-effort)
        for a_norm, p in _ALIAS_INDEX.items():
            if a_norm and a_norm in ntext:
                say_place(dispatcher, p)
                return []

        dispatcher.utter_message("Уучлаарай, тэр байршлыг олсонгүй 😅 “байршлууд” гэж бичээд жагсаалтыг хараарай.")
        return []
