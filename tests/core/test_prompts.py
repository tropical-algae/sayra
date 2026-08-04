from pathlib import Path

import pytest

from sayra.common.config import PROMPT_FILES, Settings
from sayra.core.db.models import ConversationSession
from sayra.core.enums import (
    ConversationMode,
    DifficultyLevel,
    ExamLevel,
    Language,
)
from sayra.core.prompts.loader import PromptBuilder


def test_prompt_templates_are_loaded_and_rendered_from_configuration() -> None:
    builder = PromptBuilder(Settings().PROMPT_ROOT)
    session = ConversationSession(
        native_language=Language.SIMPLIFIED_CHINESE,
        target_language=Language.ENGLISH,
        difficulty_level=DifficultyLevel.B2,
        exam_level=ExamLevel.IELTS,
        topic="Travel",
        conversation_mode=ConversationMode.GUIDED,
        suggestion_count=1,
        voice_id="voice",
        transcript_refinement_enabled=False,
        transcript_auto_submit=False,
    )

    system_prompt = builder.conversation(session, [], "Hello")[0]["content"]

    assert "Travel" in system_prompt
    assert "B2" in system_prompt
    assert "ielts" in system_prompt
    assert "Corrections are generated separately" in system_prompt


def test_prompt_mapping_is_defined_in_python_configuration() -> None:
    assert set(PROMPT_FILES) == PromptBuilder._REQUIRED
    assert all(name.endswith(".md") for name in PROMPT_FILES.values())


def test_prompt_config_validates_template_placeholders(tmp_path: Path) -> None:
    source = Settings().PROMPT_ROOT
    for template in source.glob("*.md"):
        (tmp_path / template.name).write_text(template.read_text())
    conversation = tmp_path / "conversation.md"
    conversation.write_text(conversation.read_text() + "\n$unknown_value\n")

    with pytest.raises(ValueError, match="placeholders must be"):
        PromptBuilder(tmp_path)
