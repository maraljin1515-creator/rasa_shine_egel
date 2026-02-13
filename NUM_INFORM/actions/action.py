from typing import Any, Text, Dict, List

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher


class ActionDummy(Action):
    """
    Энэ action одоогоор ашиглагдахгүй.
    Ирээдүйд:
    - нэр автоматаар оруулах
    - хичээлийн нэр асуух
    - загвар dynamic болгох
    үед ашиглана.
    """

    def name(self) -> Text:
        return "action_dummy"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any],
    ) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(
            text="Энэ бол ирээдүйд ашиглагдах custom action юм."
        )

        return []