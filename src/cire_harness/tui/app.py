from textual.app import App
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RichLog

from cire_harness.context.compactor import KEEP_MESSAGES, compact, estimate_tokens, split_point
from cire_harness.context.store import ContextStore
from cire_harness.loop.loop import run_agent
from cire_harness.providers import ProviderError, get_provider
from cire_harness.providers.types import Message, ToolCall, Usage


class ConfirmScreen(ModalScreen[bool]):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def compose(self):
        yield Label(self.text)
        yield Button("Yes", id="yes")
        yield Button("No", id="no")

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "yes")


class ChatApp(App):
    def __init__(
        self,
        provider,
        registry,
        messages: list[Message],
        session_id: str,
        store: ContextStore,
        budget: int = 8000,
    ):
        super().__init__()
        self.provider = provider
        self.registry = registry
        self.messages = messages
        self.session_id = session_id
        self.store = store
        self.budget = budget
        self.usage = Usage()

    def compose(self):
        yield RichLog(wrap=True)
        yield Input(placeholder="...")

    def on_mount(self):
        log = self.query_one(RichLog)
        for message in self.messages:
            if message.role == "user":
                log.write(f"you: {message.content}")
            elif message.role == "assistant":
                if message.content:
                    log.write(f"{message.content}")
        self.query_one(Input).focus()

    def show_event(self, event):
        log = self.query_one(RichLog)
        if isinstance(event, Message):
            log.write(f"<- {event.content[:200]}")
        else:
            if event.type == "tool_call":
                log.write(f"-> {event.tool_call.name} {event.tool_call.arguments}")
            elif event.type == "done":
                if event.response.message.content:
                    log.write(event.response.message.content)
                self.usage += event.response.usage

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.value.startswith("/"):
            response = self.handle_command(event.value)
            self.query_one(RichLog).write(response)
            event.input.value = ""
            return
        message = Message(role="user", content=event.value)
        event.input.value = ""
        self.query_one(RichLog).write(f"you: {event.value}")
        self.messages.append(message)
        self.run_worker(self.ask())

    async def approve(self, call: ToolCall) -> bool:
        return await self.push_screen_wait(ConfirmScreen(f"run {call.name} {call.arguments}?"))

    async def ask(self):
        await run_agent(
            self.provider,
            self.registry,
            self.messages,
            on_event=self.show_event,
            approve=self.approve,
            mask=lambda call, result: self.store.mask(self.session_id, call, result),
        )
        if estimate_tokens(self.messages) > self.budget:
            await self.compact()
        self.store.save_messages(self.session_id, self.messages)

    async def compact(self) -> None:
        before = estimate_tokens(self.messages)
        dropped = self.messages[: split_point(self.messages, KEEP_MESSAGES)]
        self.messages[:], summary = await compact(self.provider, self.messages)
        if summary:
            self.store.save_summary(self.session_id, summary, dropped)
            self.store.save_messages(self.session_id, self.messages)
        self.query_one(RichLog).write(
            f"compacted: ~{before} -> ~{estimate_tokens(self.messages)} tokens, "
            f"{len(self.messages)} messages"
        )

    def handle_command(self, text: str) -> str:
        cmd, *args = text.split()
        if cmd == "/stats":
            u = self.usage
            return (
                f"input={u.input_tokens} output={u.output_tokens} cached={u.cached_tokens} "
                f"context~{estimate_tokens(self.messages)}/{self.budget}"
            )
        elif cmd == "/sessions":
            return "\n".join(self.store.list_sessions())
        elif cmd == "/model":
            if not args:
                return self.provider.model
            else:
                try:
                    self.provider = get_provider(args[0])
                    return f"model: {self.provider.model}"
                except ProviderError as exc:
                    return f"error: {exc}"
        elif cmd == "/compact":
            self.run_worker(self.compact())
            return "compacting..."
        else:
            return f"unknown command: {cmd!r}"
