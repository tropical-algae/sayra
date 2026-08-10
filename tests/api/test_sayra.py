import time

from fastapi.testclient import TestClient
from sqlalchemy import select

from sayra.core.db.models import EventRecord, Turn
from sayra.core.enums import TaskStatus, TurnStatus


def test_api_routes_are_mounted_under_v1(client: TestClient) -> None:
    assert client.get("/api/v1/system/health").status_code == 200
    assert client.get("/api/system/health").status_code == 404

    paths = client.get("/openapi.json").json()["paths"]
    assert paths
    assert all(path.startswith("/api/v1/") for path in paths)


def create_session(
    client: TestClient, *, guided: bool = True, suggestions_auto_generate: bool = False
) -> dict:
    response = client.post(
        "/api/v1/sessions",
        json={
            "native_language": "zh-CN",
            "target_language": "en",
            "difficulty_level": "B1",
            "exam_level": "default",
            "topic": "School life",
            "conversation_mode": "guided" if guided else "natural",
            "suggestion_count": 1,
            "suggestions_auto_generate": suggestions_auto_generate,
            "voice_id": "test-voice",
            "transcript_refinement_enabled": True,
            "transcript_auto_submit": False,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def wait_for_turn(client: TestClient, session_id: str, turn_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/v1/sessions/{session_id}/turns/{turn_id}")
        assert response.status_code == 200
        turn = response.json()
        if turn["status"] in {"completed", "failed"}:
            return turn
        time.sleep(0.02)
    raise AssertionError("turn did not finish")


def wait_for_suggestions(client: TestClient, session_id: str, turn_id: str) -> dict:
    for _ in range(100):
        response = client.get(f"/api/v1/sessions/{session_id}/turns/{turn_id}")
        assert response.status_code == 200
        turn = response.json()
        if turn["suggestions_task_status"] in {"completed", "failed"}:
            return turn
        time.sleep(0.02)
    raise AssertionError("suggestions did not finish")


def test_complete_transcription_and_conversation_flow(
    client: TestClient, container
) -> None:
    session = create_session(client)
    session_id = session["id"]

    response = client.post(
        f"/api/v1/sessions/{session_id}/turns/transcribe",
        files={"audio": ("recording.webm", b"fake-webm", "audio/webm")},
    )
    assert response.status_code == 201, response.text
    transcript = response.json()
    assert transcript["transcript"] == "I go to school yesterday"
    assert transcript["turn"]["raw_transcript"] == transcript["transcript"]
    assert transcript["turn"]["status"] == "awaiting_confirmation"
    assert not transcript["auto_submitted"]

    user_audio = transcript["turn"]["audio_assets"][0]
    assert user_audio["content_type"] == "audio/wav"
    user_audio_path = next(
        path for path in container.storage.objects if path.endswith("/user.wav")
    )
    assert container.storage.objects[user_audio_path] == b"wav:fake-webm"
    assert container.asr.last_audio is not None
    assert container.asr.last_audio.content == b"wav:fake-webm"
    assert container.asr.last_audio.content_type == "audio/wav"

    parallel_draft = client.post(
        f"/api/v1/sessions/{session_id}/turns/transcribe",
        files={"audio": ("parallel.webm", b"parallel", "audio/webm")},
    )
    assert parallel_draft.status_code == 409

    turn_id = transcript["turn"]["id"]
    response = client.post(
        f"/api/v1/sessions/{session_id}/turns/{turn_id}/submit",
        json={
            "submitted_text": "I went to school yesterday.",
            "client_request_id": "conversation-request-1",
        },
    )
    assert response.status_code == 200, response.text

    turn = wait_for_turn(client, session_id, turn_id)
    assert turn["status"] == "completed"
    assert turn["assistant_text"].startswith("That sounds interesting")
    assert turn["assistant_translation"]
    assert turn["guidance_corrected"] == "went"
    assert turn["assistant_task_status"] == "completed"
    assert turn["audio_task_status"] == "completed"
    assert turn["suggestions_task_status"] == "skipped"
    assert turn["suggestions"] == []
    assert len(turn["audio_assets"]) == 2

    response = client.post(
        f"/api/v1/turns/{turn_id}/suggestions", json={"regenerate": False}
    )
    assert response.status_code == 202, response.text
    assert response.json()["suggestions_task_status"] == "pending"
    turn = wait_for_suggestions(client, session_id, turn_id)
    assert len(turn["suggestions"]) == 1

    async def persisted_event_types() -> list[str]:
        async with container.session_factory() as db:
            return list(
                (
                    await db.scalars(
                        select(EventRecord.event_type).where(
                            EventRecord.turn_id == turn_id
                        )
                    )
                ).all()
            )

    durable_events = client.portal.call(persisted_event_types)
    assert "assistant.text.delta" in durable_events
    assert "assistant.audio.delta" not in durable_events

    duplicate = client.post(
        f"/api/v1/sessions/{session_id}/turns/{turn_id}/submit",
        json={
            "submitted_text": "I went to school yesterday.",
            "client_request_id": "conversation-request-1",
        },
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["id"] == turn_id

    assistant_audio = next(
        asset
        for asset in turn["audio_assets"]
        if asset["asset_type"] == "assistant_reply"
    )
    response = client.get(f"/api/v1/audio/{assistant_audio['id']}")
    assert response.status_code == 200
    assert response.content.startswith(b"audio:")

    suggestion = turn["suggestions"][0]
    response = client.post(
        f"/api/v1/turns/{turn_id}/suggestions/{suggestion['id']}/audio"
    )
    assert response.status_code == 200, response.text
    assert response.json()["asset_type"] == "suggested_reply"

    history = client.get(f"/api/v1/sessions/{session_id}/turns").json()
    assert history["total"] == 1
    assert len(history["items"]) == 1
    assert (
        client.get(
            f"/api/v1/sessions/{session_id}/turns"
            f"?limit={container.config.API_MAX_PAGE_SIZE + 1}"
        ).status_code
        == 422
    )

    async def replay_all_events() -> list[tuple[int, str]]:
        replayed: list[tuple[int, str]] = []
        sequence = 0
        for _ in range(100):
            batch = await container.events.list_after(turn_id, sequence)
            if not batch:
                break
            replayed.extend((event.sequence, event.type) for event in batch)
            sequence = batch[-1].sequence
            if batch[-1].type == "turn.completed":
                break
        return replayed

    replayed = client.portal.call(replay_all_events)
    assert any(event_type == "turn.completed" for _, event_type in replayed), replayed

    with client.websocket_connect(
        f"/api/v1/sessions/{session_id}/conversation"
    ) as socket:
        socket.send_json(
            {"type": "turn.subscribe", "turn_id": turn_id, "after_sequence": 0}
        )
        event_types = []
        while True:
            event = socket.receive_json()
            event_types.append(event["type"])
            assert event["session_id"] == session_id
            if event["type"] == "turn.completed":
                break
        assert "assistant.text.delta" in event_types
        assert "assistant.audio.delta" in event_types
        socket.send_json(
            {
                "type": "turn.subscribe",
                "turn_id": turn_id,
                "after_sequence": 0,
                "phase": "auxiliary",
            }
        )
        auxiliary_event_types = []
        while True:
            event = socket.receive_json()
            auxiliary_event_types.append(event["type"])
            if event["type"] == "turn.auxiliary.completed":
                break
        assert "assistant.suggestion.completed" in auxiliary_event_types
        socket.send_json({"type": "turn.cancel"})
        protocol_error = socket.receive_json()
        assert protocol_error["type"] == "protocol.error"
        assert protocol_error["data"]["message"] == "turn_id is required"

    assert any(
        key.startswith(f"sessions/{session_id}/") for key in container.storage.objects
    )
    assert client.delete(f"/api/v1/sessions/{session_id}").status_code == 204
    assert not any(
        key.startswith(f"sessions/{session_id}/") for key in container.storage.objects
    )


def test_session_validation_and_deletion(client: TestClient) -> None:
    invalid = client.post(
        "/api/v1/sessions",
        json={
            "native_language": "en",
            "target_language": "en",
            "difficulty_level": "A1",
            "topic": "Invalid",
        },
    )
    assert invalid.status_code == 422

    session = create_session(client, guided=False)
    response = client.delete(f"/api/v1/sessions/{session['id']}")
    assert response.status_code == 204
    assert client.get(f"/api/v1/sessions/{session['id']}").status_code == 404


def test_failed_auxiliary_task_can_be_retried(client: TestClient, container) -> None:
    container.llm.fail_translation_once = True
    session = create_session(client, guided=False)
    session_id = session["id"]
    transcript = client.post(
        f"/api/v1/sessions/{session_id}/turns/transcribe",
        files={"audio": ("recording.webm", b"retry-audio", "audio/webm")},
    ).json()
    turn_id = transcript["turn"]["id"]
    client.post(
        f"/api/v1/sessions/{session_id}/turns/{turn_id}/submit",
        json={"submitted_text": "I went to school."},
    )
    turn = wait_for_turn(client, session_id, turn_id)
    assert turn["status"] == "completed"
    assert turn["translation_task_status"] == "failed"

    response = client.post(f"/api/v1/turns/{turn_id}/retry/translation")
    assert response.status_code == 202, response.text
    for _ in range(100):
        turn = client.get(f"/api/v1/sessions/{session_id}/turns/{turn_id}").json()
        if turn["translation_task_status"] == "completed":
            break
        time.sleep(0.02)
    assert turn["translation_task_status"] == "completed"
    assert turn["assistant_translation"]

    translation_traces = []
    for _ in range(100):
        traces = client.get(f"/api/v1/turns/{turn_id}/traces")
        assert traces.status_code == 200
        translation_traces = [
            item for item in traces.json() if item["step"] == "translation"
        ]
        if [item["status"] for item in translation_traces] == [
            "failed",
            "completed",
        ]:
            break
        time.sleep(0.02)
    assert [item["status"] for item in translation_traces] == ["failed", "completed"]
    assert [item["attempt"] for item in translation_traces] == [1, 2]


def test_suggestions_can_be_reused_or_regenerated(client: TestClient) -> None:
    session = create_session(client, guided=False)
    session_id = session["id"]
    draft = client.post(
        f"/api/v1/sessions/{session_id}/turns/transcribe",
        files={"audio": ("suggest.webm", b"suggest", "audio/webm")},
    ).json()
    turn_id = draft["turn"]["id"]
    client.post(
        f"/api/v1/sessions/{session_id}/turns/{turn_id}/submit",
        json={"submitted_text": "Give me another way to say this."},
    )
    wait_for_turn(client, session_id, turn_id)

    first = client.post(
        f"/api/v1/turns/{turn_id}/suggestions", json={"regenerate": False}
    )
    assert first.status_code == 202
    completed = wait_for_suggestions(client, session_id, turn_id)
    first_id = completed["suggestions"][0]["id"]

    reused = client.post(
        f"/api/v1/turns/{turn_id}/suggestions", json={"regenerate": False}
    )
    assert reused.status_code == 202
    assert reused.json()["suggestions"][0]["id"] == first_id

    regenerated = client.post(
        f"/api/v1/turns/{turn_id}/suggestions", json={"regenerate": True}
    )
    assert regenerated.status_code == 202
    assert regenerated.json()["suggestions_task_status"] in {"pending", "completed"}
    completed = wait_for_suggestions(client, session_id, turn_id)
    assert completed["suggestions"][0]["id"] != first_id

    assert client.post(f"/api/v1/turns/{turn_id}/retry/suggestions").status_code == 422


def test_session_can_auto_generate_suggestions(client: TestClient) -> None:
    session = create_session(client, guided=False, suggestions_auto_generate=True)
    assert session["suggestions_auto_generate"] is True
    session_id = session["id"]
    draft = client.post(
        f"/api/v1/sessions/{session_id}/turns/transcribe",
        files={"audio": ("auto.webm", b"auto", "audio/webm")},
    ).json()
    turn_id = draft["turn"]["id"]
    client.post(
        f"/api/v1/sessions/{session_id}/turns/{turn_id}/submit",
        json={"submitted_text": "I want some ideas."},
    )

    completed = wait_for_turn(client, session_id, turn_id)
    assert completed["assistant_translation"]
    suggested = wait_for_suggestions(client, session_id, turn_id)
    assert len(suggested["suggestions"]) == 1


def test_core_failure_releases_active_turn_constraint(
    client: TestClient, container
) -> None:
    session = create_session(client, guided=False)
    session_id = session["id"]
    draft = client.post(
        f"/api/v1/sessions/{session_id}/turns/transcribe",
        files={"audio": ("first.webm", b"first", "audio/webm")},
    ).json()
    turn_id = draft["turn"]["id"]

    container.llm.stream_delay = 0.2
    client.post(
        f"/api/v1/sessions/{session_id}/turns/{turn_id}/submit",
        json={"submitted_text": "First turn"},
    )
    conflict = client.post(
        f"/api/v1/sessions/{session_id}/turns/transcribe",
        files={"audio": ("second.webm", b"second", "audio/webm")},
    )
    assert conflict.status_code == 409
    wait_for_turn(client, session_id, turn_id)
    container.llm.stream_delay = 0.0

    second = client.post(
        f"/api/v1/sessions/{session_id}/turns/transcribe",
        files={"audio": ("second.webm", b"second", "audio/webm")},
    )
    assert second.status_code == 201
    second_id = second.json()["turn"]["id"]
    container.llm.fail_stream_once = True
    client.post(
        f"/api/v1/sessions/{session_id}/turns/{second_id}/submit",
        json={"submitted_text": "This will fail"},
    )
    failed = wait_for_turn(client, session_id, second_id)
    assert failed["status"] == "failed"
    assert failed["assistant_task_status"] == "failed"


def test_refinement_failure_falls_back_to_raw_asr(client: TestClient, container) -> None:
    container.llm.fail_refinement_once = True
    session = create_session(client)
    response = client.post(
        f"/api/v1/sessions/{session['id']}/turns/transcribe",
        files={"audio": ("fallback.webm", b"fallback", "audio/webm")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["turn"]["status"] == "awaiting_confirmation"
    assert body["turn"]["refined_transcript"] is None
    assert body["transcript"] == body["turn"]["raw_transcript"]

    traces = client.get(f"/api/v1/turns/{body['turn']['id']}/traces").json()
    refinement = next(item for item in traces if item["step"] == "refinement")
    assert refinement["status"] == "failed"


def test_restart_clears_only_regenerable_turn_outputs(
    client: TestClient, container
) -> None:
    session = create_session(client, suggestions_auto_generate=True)
    session_id = session["id"]
    draft = client.post(
        f"/api/v1/sessions/{session_id}/turns/transcribe",
        files={"audio": ("restart.webm", b"restart-audio", "audio/webm")},
    ).json()
    turn_id = draft["turn"]["id"]
    client.post(
        f"/api/v1/sessions/{session_id}/turns/{turn_id}/submit",
        json={"submitted_text": "Please recover this turn."},
    )
    wait_for_turn(client, session_id, turn_id)
    completed = wait_for_suggestions(client, session_id, turn_id)
    assert completed["assistant_text"]
    assert completed["suggestions"]

    async def mark_as_interrupted() -> None:
        async with container.session_factory() as db:
            turn = await db.get(Turn, turn_id)
            assert turn is not None
            turn.status = TurnStatus.QUEUED
            turn.audio_task_status = TaskStatus.COMPLETED
            turn.translation_task_status = TaskStatus.COMPLETED
            turn.suggestions_task_status = TaskStatus.COMPLETED
            turn.guidance_task_status = TaskStatus.COMPLETED
            await db.commit()

    client.portal.call(mark_as_interrupted)
    client.portal.call(container.workflow._start_turn, turn_id)

    recovered = client.get(f"/api/v1/sessions/{session_id}/turns/{turn_id}").json()
    assert recovered["status"] == "processing"
    assert recovered["submitted_text"] == "Please recover this turn."
    assert recovered["assistant_text"] is None
    assert recovered["assistant_translation"] is None
    assert recovered["suggestions"] == []
    assert [asset["asset_type"] for asset in recovered["audio_assets"]] == [
        "user_recording"
    ]
    assert recovered["assistant_task_status"] == "running"
    assert recovered["audio_task_status"] == "pending"

    async def finish_cleanup() -> None:
        async with container.session_factory() as db:
            turn = await db.get(Turn, turn_id)
            assert turn is not None
            turn.status = TurnStatus.CANCELLED
            await db.commit()

    client.portal.call(finish_cleanup)
    assert client.delete(f"/api/v1/sessions/{session_id}").status_code == 204
