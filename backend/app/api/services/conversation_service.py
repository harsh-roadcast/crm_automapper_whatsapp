import re
from dataclasses import dataclass, field
from typing import Literal

from backend.app.models.lead import LeadStatus


EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


@dataclass(frozen=True, slots=True)
class Choice:
    id: str
    label: str
    title: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class Prompt:
    key: str
    text: str
    kind: Literal["text", "list", "buttons"]
    options: tuple[Choice, ...] = ()


@dataclass(slots=True)
class ConversationState:
    current_step: str = "welcome"
    responses: dict[str, str | list[str]] = field(default_factory=dict)


@dataclass(slots=True)
class ConversationTurnResult:
    current_step: str
    prompts: list[Prompt]
    responses: dict[str, str | list[str]]
    lead_status: LeadStatus
    is_complete: bool = False


FLEET_SIZE_CHOICES = (
    Choice(
        "super_large",
        "Super Large Fleet — More than 500 vehicles/assets",
        "500+",
        "Super Large Fleet",
    ),
    Choice(
        "large",
        "Large Fleet — 100 to 500 vehicles/assets",
        "100-500",
        "Large Fleet",
    ),
    Choice(
        "medium",
        "Medium Fleet — 20 to 100 vehicles/assets",
        "20-100",
        "Medium Fleet",
    ),
    Choice(
        "small",
        "Small Fleet — Less than 20 vehicles/assets",
        "<20",
        "Small Fleet",
    ),
)

PAIN_POINT_CHOICES = (
    Choice("visibility", "Real-time fleet visibility & tracking", "Tracking"),
    Choice("fuel", "Fuel theft or fuel consumption monitoring", "Fuel"),
    Choice("accident", "Accident proof & video evidence", "Accident"),
    Choice("cargo", "Goods/cargo theft prevention", "Cargo"),
    Choice("driver", "Driver behaviour & fatigue detection", "Driver"),
    Choice("route", "Route deviation & compliance", "Route"),
    Choice("compliance", "Regulatory compliance (MoRTH, AIS-140, etc.)", "Compliance"),
    Choice("health", "Vehicle health & breakdown prevention", "Vehicle Health"),
    Choice("reporting", "Trip reporting & documentation", "Trip Reports"),
    Choice("insurance", "Insurance & liability management", "Insurance"),
    Choice("other", "Other", "Other", "Share your requirement"),
)

YES_NO_CHOICES = (
    Choice("yes", "Yes, add another", "Yes"),
    Choice("no", "No, continue", "No"),
)

MORE_PAIN_POINTS_CHOICE = Choice("__more__", "More options", "More", "See more options")
BACK_PAIN_POINTS_CHOICE = Choice("__back__", "Back to first options", "Back", "Return to first options")


class ConversationService:
    def start_conversation(self, state: ConversationState | None = None) -> ConversationTurnResult:
        conversation_state = state or ConversationState()
        conversation_state.current_step = "ask_name"
        prompts = [
            Prompt(
                key="welcome",
                kind="text",
                text=(
                    "Hi! Welcome to Roadcast. We help fleet operators track, protect, "
                    "and optimise their vehicles with AI-powered telematics. "
                    "Let's get you connected with the right person."
                ),
            ),
            Prompt(
                key="ask_name",
                kind="text",
                text="What is your name?",
            ),
        ]
        return self._build_result(conversation_state, prompts)

    def advance(self, message_text: str, state: ConversationState) -> ConversationTurnResult:
        incoming_text = message_text.strip()
        if state.current_step == "welcome":
            return self.start_conversation(state)

        if state.current_step == "ask_name":
            if not incoming_text:
                return self._error_result(state, "Please share your name to continue.")
            state.responses["name"] = incoming_text
            state.current_step = "ask_fleet_size"
            return self._build_result(state, [self._fleet_size_prompt()])

        if state.current_step == "ask_fleet_size":
            selected_choice = self._match_choice(incoming_text, FLEET_SIZE_CHOICES)
            if selected_choice is None:
                return self._error_result(state, "Please choose one of the listed fleet-size options.")
            state.responses["fleet_size"] = selected_choice.label
            state.current_step = "ask_company_name"
            return self._build_result(
                state,
                [Prompt(key="ask_company_name", kind="text", text="What is your company name?")],
            )

        if state.current_step == "ask_company_name":
            if not incoming_text:
                return self._error_result(state, "Please share your company name to continue.")
            state.responses["company_name"] = incoming_text
            state.current_step = "ask_work_email"
            return self._build_result(
                state,
                [Prompt(key="ask_work_email", kind="text", text="What is your work email ID?")],
            )

        if state.current_step == "ask_work_email":
            if not EMAIL_PATTERN.match(incoming_text):
                return self._error_result(state, "Please share a valid work email address.")
            state.responses["work_email"] = incoming_text
            state.current_step = "ask_pain_point"
            state.responses["_pain_point_page"] = "primary"
            return self._build_result(state, [self._pain_point_prompt(state)])

        if state.current_step == "ask_pain_point":
            selected_choice = self._match_choice(incoming_text, self._available_pain_point_choices(state))
            if selected_choice is None:
                selected_choice = self._match_choice(incoming_text, self._pain_point_navigation_choices(state))
            if selected_choice and selected_choice.id == MORE_PAIN_POINTS_CHOICE.id:
                state.responses["_pain_point_page"] = "secondary"
                return self._build_result(state, [self._pain_point_prompt(state)])
            if selected_choice and selected_choice.id == BACK_PAIN_POINTS_CHOICE.id:
                state.responses["_pain_point_page"] = "primary"
                return self._build_result(state, [self._pain_point_prompt(state)])
            if selected_choice is None:
                return self._error_result(state, "Please choose one of the listed problem options.")
            self._append_pain_point(state, selected_choice.label)
            state.responses["_pain_point_page"] = "primary"
            if selected_choice.id == "other":
                state.current_step = "ask_other_problem_text"
                return self._build_result(
                    state,
                    [
                        Prompt(
                            key="ask_other_problem_text",
                            kind="text",
                            text="Please describe the other problem you want to solve.",
                        )
                    ],
                )
            state.current_step = "ask_additional_pain_point"
            return self._build_result(state, [self._add_another_prompt()])

        if state.current_step == "ask_other_problem_text":
            if not incoming_text:
                return self._error_result(state, "Please describe the other problem so we can map it correctly.")
            state.responses["other_problem_text"] = incoming_text
            state.current_step = "ask_additional_pain_point"
            return self._build_result(state, [self._add_another_prompt()])

        if state.current_step == "ask_additional_pain_point":
            selected_choice = self._match_choice(incoming_text, YES_NO_CHOICES)
            if selected_choice is None:
                return self._error_result(state, "Please choose whether you want to add another problem area.")
            if selected_choice.id == "yes" and self._available_pain_point_choices(state):
                state.current_step = "ask_pain_point"
                state.responses["_pain_point_page"] = "primary"
                return self._build_result(state, [self._pain_point_prompt(state)])
            state.current_step = "completed"
            return self._complete(state)

        return self._complete(state)

    def build_lead_payload(self, whatsapp_number: str, state: ConversationState) -> dict[str, str | list[str]]:
        return {
            "whatsapp_number": whatsapp_number,
            "name": str(state.responses.get("name", "")),
            "fleet_size": str(state.responses.get("fleet_size", "")),
            "company_name": str(state.responses.get("company_name", "")),
            "work_email": str(state.responses.get("work_email", "")),
            "pain_points": list(state.responses.get("pain_points", [])),
            "other_problem_text": str(state.responses.get("other_problem_text", "")),
            "last_question_key": state.current_step,
            "lead_status": self._current_status(state).value,
        }

    def _fleet_size_prompt(self) -> Prompt:
        return Prompt(
            key="ask_fleet_size",
            kind="list",
            text="How large is your fleet?",
            options=FLEET_SIZE_CHOICES,
        )

    def _pain_point_prompt(self, state: ConversationState) -> Prompt:
        available_choices = self._pain_point_choices_for_page(state)
        return Prompt(
            key="ask_pain_point",
            kind="list",
            text="Which problem are you looking to solve first?",
            options=tuple(available_choices),
        )

    def _add_another_prompt(self) -> Prompt:
        return Prompt(
            key="ask_additional_pain_point",
            kind="buttons",
            text="Would you like to add another problem area?",
            options=YES_NO_CHOICES,
        )

    def _complete(self, state: ConversationState) -> ConversationTurnResult:
        closing_message = Prompt(
            key="completed",
            kind="text",
            text=(
                f"Thank you, {state.responses.get('name', 'there')}! "
                "One of our fleet intelligence experts will reach out to you shortly on this number. "
                "In the meantime, feel free to explore what we do at www.roadcast.in"
            ),
        )
        return self._build_result(state, [closing_message], is_complete=True)

    def _build_result(
        self,
        state: ConversationState,
        prompts: list[Prompt],
        *,
        is_complete: bool = False,
    ) -> ConversationTurnResult:
        return ConversationTurnResult(
            current_step=state.current_step,
            prompts=prompts,
            responses=state.responses,
            lead_status=self._current_status(state),
            is_complete=is_complete,
        )

    def _error_result(self, state: ConversationState, error_text: str) -> ConversationTurnResult:
        current_prompt = self._prompt_for_current_step(state)
        prompts = [Prompt(key="error", kind="text", text=error_text)]
        if current_prompt is not None:
            prompts.append(current_prompt)
        return self._build_result(state, prompts)

    def _prompt_for_current_step(self, state: ConversationState) -> Prompt | None:
        if state.current_step == "ask_name":
            return Prompt(key="ask_name", kind="text", text="What is your name?")
        if state.current_step == "ask_fleet_size":
            return self._fleet_size_prompt()
        if state.current_step == "ask_company_name":
            return Prompt(key="ask_company_name", kind="text", text="What is your company name?")
        if state.current_step == "ask_work_email":
            return Prompt(key="ask_work_email", kind="text", text="What is your work email ID?")
        if state.current_step == "ask_pain_point":
            return self._pain_point_prompt(state)
        if state.current_step == "ask_other_problem_text":
            return Prompt(
                key="ask_other_problem_text",
                kind="text",
                text="Please describe the other problem you want to solve.",
            )
        if state.current_step == "ask_additional_pain_point":
            return self._add_another_prompt()
        return None

    def _append_pain_point(self, state: ConversationState, pain_point_label: str) -> None:
        pain_points = state.responses.setdefault("pain_points", [])
        if isinstance(pain_points, list) and pain_point_label not in pain_points:
            pain_points.append(pain_point_label)

    def _available_pain_point_choices(self, state: ConversationState) -> list[Choice]:
        selected_pain_points = state.responses.get("pain_points", [])
        if not isinstance(selected_pain_points, list):
            return list(PAIN_POINT_CHOICES)
        return [choice for choice in PAIN_POINT_CHOICES if choice.label not in selected_pain_points]

    def _pain_point_choices_for_page(self, state: ConversationState) -> list[Choice]:
        available_choices = self._available_pain_point_choices(state)
        current_page = str(state.responses.get("_pain_point_page", "primary"))
        if len(available_choices) <= 9:
            state.responses["_pain_point_page"] = "primary"
            return available_choices
        if current_page == "secondary":
            remaining_choices = available_choices[9:]
            return [*remaining_choices, BACK_PAIN_POINTS_CHOICE]
        return [*available_choices[:9], MORE_PAIN_POINTS_CHOICE]

    def _pain_point_navigation_choices(self, state: ConversationState) -> list[Choice]:
        choices = []
        current_page = str(state.responses.get("_pain_point_page", "primary"))
        available_choices = self._available_pain_point_choices(state)
        if len(available_choices) > 9 and current_page == "primary":
            choices.append(MORE_PAIN_POINTS_CHOICE)
        if len(available_choices) > 9 and current_page == "secondary":
            choices.append(BACK_PAIN_POINTS_CHOICE)
        return choices

    def _match_choice(self, incoming_text: str, choices: tuple[Choice, ...] | list[Choice]) -> Choice | None:
        normalized_text = self._normalize(incoming_text)
        for choice in choices:
            candidates = {self._normalize(choice.id), self._normalize(choice.label), self._normalize(choice.title)}
            if choice.description:
                candidates.add(self._normalize(choice.description))
            if normalized_text in candidates:
                return choice
        return None

    def _normalize(self, value: str) -> str:
        return " ".join(value.casefold().strip().split())

    def _current_status(self, state: ConversationState) -> LeadStatus:
        if state.current_step == "completed":
            return LeadStatus.qualified
        return LeadStatus.in_progress