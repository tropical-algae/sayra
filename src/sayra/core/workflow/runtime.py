import asyncio

from loguru import logger

from sayra.core.db.crud import runtime as runtime_crud
from sayra.core.enums import AuxiliaryTask
from sayra.core.workflow.conversation import ConversationWorkflow


class WorkflowRuntime:
    """Owns workflow tasks independently from WebSocket connections."""

    def __init__(self, workflow: ConversationWorkflow) -> None:
        self.workflow = workflow
        self._tasks: dict[str, asyncio.Task] = {}

    def start(self, turn_id: str) -> None:
        existing = self._tasks.get(turn_id)
        if existing and not existing.done():
            return
        task = asyncio.create_task(self._run(turn_id), name=f"turn:{turn_id}")
        self._tasks[turn_id] = task
        task.add_done_callback(lambda completed: self._forget(turn_id, completed))

    def start_retry(self, turn_id: str, task_name: AuxiliaryTask) -> None:
        key = f"{turn_id}:retry:{task_name.value}"
        existing = self._tasks.get(key)
        if existing and not existing.done():
            return
        task = asyncio.create_task(
            self._run_retry(turn_id, task_name), name=f"retry:{task_name.value}:{turn_id}"
        )
        self._tasks[key] = task
        task.add_done_callback(lambda completed: self._forget(key, completed))

    def _forget(self, key: str, completed: asyncio.Task) -> None:
        if self._tasks.get(key) is completed:
            self._tasks.pop(key, None)

    async def recover(self) -> None:
        """Recover durable workflow state before the API starts accepting traffic."""
        async with self.workflow.session_factory() as db:
            turn_ids = await runtime_crud.update_interrupted_tasks_and_select_recoverable_turn_ids(
                db
            )
        for turn_id in turn_ids:
            self.start(turn_id)

    async def _run(self, turn_id: str) -> None:
        try:
            await self.workflow.run(turn_id=turn_id)
        except Exception:
            logger.exception("Uncaught workflow error for turn {}", turn_id)

    async def _run_retry(self, turn_id: str, task_name: AuxiliaryTask) -> None:
        try:
            await self.workflow.retry_auxiliary(turn_id, task_name)
        except Exception:
            logger.exception(
                "Auxiliary retry {} failed for turn {}", task_name.value, turn_id
            )

    async def cancel(self, turn_id: str) -> bool:
        task = self._tasks.get(turn_id)
        if not task or task.done():
            return False
        task.cancel()
        return True

    async def shutdown(self, grace_seconds: float) -> None:
        if not self._tasks:
            return
        _, pending = await asyncio.wait(self._tasks.values(), timeout=grace_seconds)
        task_keys = {task: key for key, task in self._tasks.items()}
        for task in pending:
            key = task_keys.get(task, "")
            if ":retry:" not in key:
                self.workflow.preserve_for_restart(key)
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
