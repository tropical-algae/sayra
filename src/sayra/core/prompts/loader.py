from pathlib import Path
from string import Template
from typing import ClassVar

from sayra.common.config import PROMPT_FILES
from sayra.core.db.models import ConversationSession, Turn
from sayra.core.enums import ConversationMode


class PromptBuilder:
    """Loads validated Markdown templates once and builds provider messages."""

    _REQUIRED: ClassVar[set[str]] = {
        "conversation",
        "mode_guided",
        "mode_natural",
        "refinement",
        "translation",
        "suggestions",
        "guidance",
        "summary",
        "summary_turn",
    }
    _VARIABLES: ClassVar[dict[str, set[str]]] = {
        "conversation": {
            "target_language",
            "difficulty_level",
            "exam_level",
            "topic",
            "mode_instruction",
            "conversation_summary",
        },
        "mode_guided": set(),
        "mode_natural": set(),
        "refinement": {"target_language", "topic"},
        "translation": {"native_language"},
        "suggestions": {
            "suggestion_count",
            "target_language",
            "native_language",
            "difficulty_level",
            "exam_level",
        },
        "guidance": {"native_language"},
        "summary": {"existing_summary", "new_turns"},
        "summary_turn": {"submitted_text", "assistant_text"},
    }

    def __init__(self, prompt_root: Path) -> None:
        template_root = prompt_root.expanduser().resolve()
        missing = self._REQUIRED - PROMPT_FILES.keys()
        if missing:
            raise ValueError(f"Prompt mapping is missing: {', '.join(sorted(missing))}")

        self._templates: dict[str, Template] = {}
        for name in self._REQUIRED:
            filename = PROMPT_FILES[name]
            if not filename.endswith(".md"):
                raise ValueError(f"Prompt {name} must reference a Markdown file")
            template_path = (template_root / filename).resolve()
            if not template_path.is_relative_to(template_root):
                raise ValueError(f"Prompt {name} escapes the template directory")
            template = Template(template_path.read_text(encoding="utf-8").strip())
            if not template.is_valid():
                raise ValueError(f"Prompt {name} contains an invalid placeholder")
            identifiers = set(template.get_identifiers())
            if identifiers != self._VARIABLES[name]:
                raise ValueError(
                    f"Prompt {name} placeholders must be "
                    f"{sorted(self._VARIABLES[name])}, got {sorted(identifiers)}"
                )
            self._templates[name] = template

    def _render(self, name: str, **values: object) -> str:
        return self._templates[name].substitute(
            {key: str(value) for key, value in values.items()}
        )

    def conversation(
        self,
        session: ConversationSession,
        history: list[Turn],
        current_text: str,
    ) -> list[dict[str, str]]:
        mode_name = (
            "mode_guided"
            if session.conversation_mode == ConversationMode.GUIDED
            else "mode_natural"
        )
        system = self._render(
            "conversation",
            target_language=session.target_language.value,
            difficulty_level=session.difficulty_level.value,
            exam_level=session.exam_level.value,
            topic=session.topic,
            mode_instruction=self._render(mode_name),
            conversation_summary=session.conversation_summary or "",
        )
        messages = [{"role": "system", "content": system}]
        for turn in history:
            if turn.submitted_text and turn.assistant_text:
                messages.extend(
                    [
                        {"role": "user", "content": turn.submitted_text},
                        {"role": "assistant", "content": turn.assistant_text},
                    ]
                )
        messages.append({"role": "user", "content": current_text})
        return messages

    def refinement(
        self, session: ConversationSession, raw_transcript: str
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": self._render(
                    "refinement",
                    target_language=session.target_language.value,
                    topic=session.topic,
                ),
            },
            {"role": "user", "content": raw_transcript},
        ]

    def translation(
        self, session: ConversationSession, assistant_text: str
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": self._render(
                    "translation", native_language=session.native_language.value
                ),
            },
            {"role": "user", "content": assistant_text},
        ]

    def suggestions(
        self, session: ConversationSession, assistant_text: str
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": self._render(
                    "suggestions",
                    suggestion_count=session.suggestion_count,
                    target_language=session.target_language.value,
                    native_language=session.native_language.value,
                    difficulty_level=session.difficulty_level.value,
                    exam_level=session.exam_level.value,
                ),
            },
            {"role": "user", "content": assistant_text},
        ]

    def guidance(
        self, session: ConversationSession, submitted_text: str
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": self._render(
                    "guidance", native_language=session.native_language.value
                ),
            },
            {"role": "user", "content": submitted_text},
        ]

    def summary(
        self, existing_summary: str | None, turns: list[Turn]
    ) -> list[dict[str, str]]:
        transcript = "\n\n".join(
            self._render(
                "summary_turn",
                submitted_text=turn.submitted_text or "",
                assistant_text=turn.assistant_text or "",
            )
            for turn in turns
        )
        return [
            {
                "role": "system",
                "content": self._render(
                    "summary",
                    existing_summary=existing_summary or "",
                    new_turns=transcript,
                ),
            }
        ]
