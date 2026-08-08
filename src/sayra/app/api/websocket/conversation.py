import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from pydantic import ValidationError

from sayra.app.api.deps import Container
from sayra.app.schemas.websocket import ClientEvent, ServerEvent
from sayra.app.services import turn_service
from sayra.core.exceptions import SayraError

router = APIRouter()


@router.websocket("/{session_id}/conversation")
async def conversation_socket(
    websocket: WebSocket,
    session_id: str,
    container: Container,
) -> None:
    await websocket.accept()
    send_lock = asyncio.Lock()
    subscriptions: dict[str, asyncio.Task] = {}

    async def send(event: ServerEvent) -> None:
        async with send_lock:
            await websocket.send_json(event.model_dump(mode="json"))

    async def subscribe(turn_id: str, after_sequence: int) -> None:
        async for event in container.events.subscribe(
            session_id, turn_id, after_sequence
        ):
            await send(event)

    async def start_subscription(turn_id: str, after_sequence: int) -> None:
        previous = subscriptions.get(turn_id)
        if previous and not previous.done():
            previous.cancel()
            await asyncio.gather(previous, return_exceptions=True)
        task = asyncio.create_task(subscribe(turn_id, after_sequence))
        subscriptions[turn_id] = task

        def subscription_done(completed: asyncio.Task) -> None:
            if subscriptions.get(turn_id) is completed:
                subscriptions.pop(turn_id, None)
            if not completed.cancelled() and (error := completed.exception()):
                logger.debug(f"WebSocket subscription {turn_id} ended: {error}")

        task.add_done_callback(subscription_done)

    async def send_protocol_error(message: str) -> None:
        await websocket.send_json(
            {"type": "protocol.error", "data": {"message": message}}
        )

    try:
        while True:
            try:
                client_event = ClientEvent.model_validate(await websocket.receive_json())
            except (ValidationError, ValueError) as exc:
                await send_protocol_error(str(exc))
                continue
            try:
                async with container.session_factory() as db:
                    if client_event.type == "turn.submit":
                        if not client_event.submitted_text:
                            await send_protocol_error("submitted_text is required")
                            continue
                        turn = await turn_service.submit_turn(
                            db,
                            container.workflow,
                            session_id,
                            client_event.submitted_text,
                            client_event.turn_id,
                            client_event.client_request_id,
                        )
                        await start_subscription(turn.id, client_event.after_sequence)
                    elif client_event.type == "turn.subscribe":
                        if not client_event.turn_id:
                            await send_protocol_error("turn_id is required")
                            continue
                        await turn_service.get_turn(db, session_id, client_event.turn_id)
                        await start_subscription(
                            client_event.turn_id, client_event.after_sequence
                        )
                    elif client_event.type == "turn.cancel":
                        if not client_event.turn_id:
                            await send_protocol_error("turn_id is required")
                            continue
                        await turn_service.get_turn(db, session_id, client_event.turn_id)
                        if not await container.workflow.cancel(client_event.turn_id):
                            await send_protocol_error("turn is not running")
            except SayraError as exc:
                await send_protocol_error(str(exc))
    except WebSocketDisconnect:
        pass
    finally:
        tasks = list(subscriptions.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
