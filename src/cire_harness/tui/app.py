import asyncio

from textual.app import App
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RichLog, Static

from cire_harness.config import MCPServer
from cire_harness.context.compactor import KEEP_MESSAGES, compact, estimate_tokens, split_point
from cire_harness.context.store import ContextStore
from cire_harness.loop.loop import run_agent
from cire_harness.mcp.client import MCPManager
from cire_harness.providers import ProviderError, get_provider
from cire_harness.providers.types import Message, ToolCall, Usage

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


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
    BINDINGS = [("escape", "stop", "Stop")]

    def __init__(
        self,
        provider,
        registry,
        messages: list[Message],
        session_id: str,
        store: ContextStore,
        budget: int = 8000,
        mcp_servers: dict[str, MCPServer] | None = None,
    ):
        super().__init__()
        self.provider = provider
        self.registry = registry
        self.messages = messages
        self.session_id = session_id
        self.store = store
        self.budget = budget
        self.usage = Usage()
        self.worker = None
        self.mcp_servers = mcp_servers or {}
        self.mcp = MCPManager()
        self.mcp_ready = asyncio.Event()
        self.mcp_closing = asyncio.Event()
        self.state = ""
        self.partial = ""
        self.frame = 0

    def compose(self):
        yield RichLog(wrap=True)
        yield Static(id="status")
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
        self.set_interval(0.1, self.tick)
        self.mcp_task = asyncio.create_task(self.mcp_lifecycle())

    async def mcp_lifecycle(self):
        try:
            tools = await self.mcp.connect(self.mcp_servers)
            self.registry.tools.update({t.name: t for t in tools})
            for name, error in self.mcp.errors.items():
                self.query_one(RichLog).write(f"mcp {name}: {error}")
        finally:
            self.mcp_ready.set()
        await self.mcp_closing.wait()
        await self.mcp.close()

    async def on_unmount(self):
        self.mcp_closing.set()
        await self.mcp_task

    def tick(self):
        if not self.state:
            self.query_one("#status", Static).update("")
            return
        self.frame = (self.frame + 1) % len(FRAMES)
        text = f"{FRAMES[self.frame]} {self.state}  (esc to stop)"
        if self.partial:
            text += "\n" + self.partial[-500:]
        self.query_one("#status", Static).update(text)

    def show_event(self, event):
        log = self.query_one(RichLog)
        if isinstance(event, Message):
            log.write(f"<- {event.content[:200]}")
            self.state = "thinking"
        elif event.type == "text":
            self.partial += event.text
        elif event.type == "tool_call":
            log.write(f"-> {event.tool_call.name} {event.tool_call.arguments}")
            self.state = f"running {event.tool_call.name}"
        elif event.type == "done":
            self.partial = ""
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
        self.worker = self.run_worker(self.ask())

    def action_stop(self) -> None:
        if self.worker is not None and self.worker.is_running:
            self.worker.cancel()

    async def approve(self, call: ToolCall) -> bool:
        return await self.push_screen_wait(ConfirmScreen(f"run {call.name} {call.arguments}?"))

    async def ask(self):
        self.state = "connecting mcp"
        await self.mcp_ready.wait()
        self.state = "thinking"
        try:
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
        except asyncio.CancelledError:
            while self.messages and self.messages[-1].role != "user":
                self.messages.pop()
            if self.is_running:
                self.query_one(RichLog).write("stopped")
        except ProviderError as exc:
            self.query_one(RichLog).write(f"error: {exc}")
        finally:
            self.state = ""
            self.partial = ""
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
        elif cmd == "/tools":
            return "\n".join(
                f"{t.name}{' (confirm)' if t.risky else ''}" for t in self.registry.tools.values()
            )
        elif cmd == "/compact":
            self.run_worker(self.compact())
            return "compacting..."
        else:
            return f"unknown command: {cmd!r}"
