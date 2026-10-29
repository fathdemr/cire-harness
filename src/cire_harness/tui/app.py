import asyncio

from rich.markdown import Markdown
from rich.text import Text
from textual.app import App
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import ModalScreen
from textual.selection import Selection
from textual.suggester import SuggestFromList
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static

from cire_harness.config import MCPServer
from cire_harness.context.compactor import KEEP_MESSAGES, compact, estimate_tokens, split_point
from cire_harness.context.store import ContextStore
from cire_harness.loop.loop import run_agent
from cire_harness.mcp.client import MCPManager
from cire_harness.providers import ProviderError, get_provider
from cire_harness.providers.types import Message, ToolCall, Usage
from cire_harness.telemetry import Metered

FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
COMMANDS = {
    "/model": "show the planner model, or switch: /model provider:model",
    "/tools": "list loaded tools, (confirm) marks ones that ask first",
    "/stats": "token usage, context size and executor usage",
    "/sessions": "list saved sessions, newest first",
    "/compact": "summarise older messages to free context",
    "/copy": "copy the last answer to the clipboard",
    "/help": "show this list",
}


class Log(RichLog):
    def get_selection(self, selection: Selection) -> tuple[str, str] | None:
        text = "\n".join(strip.text for strip in self.lines)
        return selection.extract(text), "\n"

    def selection_updated(self, selection: Selection | None) -> None:
        self._line_cache.clear()
        self.refresh()


class ConfirmScreen(ModalScreen[bool]):
    DEFAULT_CSS = """
    ConfirmScreen { align: center middle; }
    ConfirmScreen > Static { width: 70; height: auto; border: round $warning; padding: 1 2;
        background: $surface; }
    ConfirmScreen Label { width: 100%; margin-bottom: 1; }
    ConfirmScreen Horizontal { height: auto; align: center middle; }
    ConfirmScreen Button { margin: 0 2; }
    """
    BINDINGS = [
        ("y", "answer(True)", "Yes"),
        ("n", "answer(False)", "No"),
        ("escape", "answer(False)", "No"),
    ]

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text

    def compose(self):
        with Static():
            yield Label(self.text)
            with Horizontal():
                yield Button("Yes (y)", id="yes", variant="warning")
                yield Button("No (n)", id="no")

    def action_answer(self, value: bool) -> None:
        self.dismiss(value)

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss(event.button.id == "yes")


class ChatApp(App):
    TITLE = "cire"
    CSS = """
    Screen { layout: vertical; }
    Log { height: 1fr; padding: 0 1; }
    #hint { height: auto; max-height: 9; padding: 0 2; color: $text-muted; background: $surface;
        display: none; }
    #status { height: auto; max-height: 6; padding: 0 2; color: $text-muted; }
    Input { border: round $primary; }
    Input:focus { border: round $accent; }
    """
    BINDINGS = [
        Binding("escape", "stop", "Stop"),
        Binding("ctrl+q", "quit", "Quit", priority=True),
    ]

    def __init__(
        self,
        provider,
        registry,
        messages: list[Message],
        session_id: str,
        store: ContextStore,
        budget: int = 8000,
        mcp_servers: dict[str, MCPServer] | None = None,
        delegate=None,
    ):
        super().__init__()
        self.provider = provider
        self.registry = registry
        self.messages = messages
        self.session_id = session_id
        self.store = store
        self.budget = budget
        self.usage = Usage()
        self.exec_usage = Usage()
        self.delegate = delegate
        self.worker = None
        self.mcp_servers = mcp_servers or {}
        self.mcp = MCPManager()
        self.mcp_ready = asyncio.Event()
        self.mcp_closing = asyncio.Event()
        self.state = ""
        self.partial = ""
        self.frame = 0

    def compose(self):
        yield Header()
        yield Log(wrap=True, markup=False)
        yield Static(id="hint")
        yield Static(id="status")
        yield Input(
            placeholder="Type a message, / for commands",
            suggester=SuggestFromList(list(COMMANDS), case_sensitive=False),
        )
        yield Footer()

    def on_mount(self):
        self.sub_title = f"{self.provider.model}  ·  session {self.session_id}"
        log = self.query_one(RichLog)
        for message in self.messages:
            if message.role == "user":
                log.write(Text.assemble(("you: ", "bold cyan"), message.content))
            elif message.role == "assistant" and message.content:
                log.write(Markdown(message.content))
        self.query_one(Input).focus()
        self.status = self.query_one("#status", Static)
        if self.delegate is not None:
            tool = self.delegate(self.approve, lambda e: self.show_event(e, "exec"))
            self.registry.tools[tool.name] = tool
        self.set_interval(0.1, self.tick)
        self.mcp_task = asyncio.create_task(self.mcp_lifecycle())

    async def mcp_lifecycle(self):
        try:
            tools = await self.mcp.connect(self.mcp_servers)
            self.registry.tools.update({t.name: t for t in tools})
            for name, error in self.mcp.errors.items():
                self.query_one(RichLog).write(Text(f"mcp {name}: {error}", style="red"))
        finally:
            self.mcp_ready.set()
        await self.mcp_closing.wait()
        await self.mcp.close()

    async def on_unmount(self):
        self.mcp_closing.set()
        await self.mcp_task

    def tick(self):
        if not self.state:
            self.status.update("")
            return
        self.frame = (self.frame + 1) % len(FRAMES)
        text = f"{FRAMES[self.frame]} {self.state}  (esc to stop)"
        if self.partial:
            text += "\n" + self.partial[-500:]
        self.status.update(text)

    def show_event(self, event, role: str = ""):
        log = self.query_one(RichLog)
        tag = f"[{role}] " if role else ""
        tag_style = "bold magenta"
        if isinstance(event, Message):
            style = "red" if event.content.startswith("error:") else "dim"
            log.write(Text.assemble((tag, tag_style), (f"<- {event.content[:200]}", style)))
            self.state = f"{role or 'thinking'}"
        elif event.type == "text":
            self.partial += event.text
        elif event.type == "tool_call":
            call = f"-> {event.tool_call.name} {event.tool_call.arguments}"
            log.write(Text.assemble((tag, tag_style), (call, "yellow")))
            self.state = f"{tag}running {event.tool_call.name}"
        elif event.type == "done":
            self.partial = ""
            if event.response.message.content:
                if role:
                    log.write(Text.assemble((tag, tag_style), event.response.message.content))
                else:
                    log.write(Markdown(event.response.message.content))
            if role:
                self.exec_usage += event.response.usage
            else:
                self.usage += event.response.usage

    def on_input_changed(self, event: Input.Changed) -> None:
        hint = self.query_one("#hint", Static)
        text = event.value
        if not text.startswith("/") or " " in text:
            hint.display = False
            return
        matches = [c for c in COMMANDS if c.startswith(text.lower())]
        if not matches:
            hint.display = False
            return
        hint.update("\n".join(f"{c:<11}{COMMANDS[c]}" for c in matches))
        hint.display = True

    def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        event.input.value = ""
        self.query_one("#hint", Static).display = False
        if not text:
            return
        if text.startswith("/"):
            response = self.handle_command(text)
            style = "red" if response.startswith(("error:", "unknown")) else "green"
            self.query_one(RichLog).write(Text(response, style=style))
            return
        message = Message(role="user", content=text)
        self.query_one(RichLog).write(Text.assemble(("you: ", "bold cyan"), text))
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
                self.query_one(RichLog).write(Text("stopped", style="yellow"))
        except ProviderError as exc:
            self.query_one(RichLog).write(Text(f"error: {exc}", style="red"))
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
            Text(
                f"compacted: ~{before} -> ~{estimate_tokens(self.messages)} tokens, "
                f"{len(self.messages)} messages",
                style="yellow",
            )
        )

    def handle_command(self, text: str) -> str:
        cmd, *args = text.split()
        if cmd == "/stats":
            u, e = self.usage, self.exec_usage
            text = (
                f"input={u.input_tokens} output={u.output_tokens} cached={u.cached_tokens} "
                f"context~{estimate_tokens(self.messages)}/{self.budget}"
            )
            if e != Usage():
                text += (
                    f"\nexecutor: input={e.input_tokens} output={e.output_tokens} "
                    f"cached={e.cached_tokens}"
                )
            return text
        elif cmd == "/sessions":
            return "\n".join(self.store.list_sessions())
        elif cmd == "/model":
            if not args:
                return self.provider.model
            else:
                try:
                    self.provider = Metered(
                        get_provider(args[0]),
                        "planner",
                        lambda r: self.store.save_call(self.session_id, r),
                    )
                    self.sub_title = f"{self.provider.model}  ·  session {self.session_id}"
                    return f"model: {self.provider.model}"
                except ProviderError as exc:
                    return f"error: {exc}"
        elif cmd == "/help":
            return "\n".join(f"{c:<11}{d}" for c, d in COMMANDS.items())
        elif cmd == "/copy":
            last = next((m.content for m in reversed(self.messages) if m.role == "assistant"), "")
            if not last:
                return "nothing to copy"
            self.copy_to_clipboard(last)
            return f"copied {len(last)} chars"
        elif cmd == "/tools":
            return "\n".join(
                f"{t.name}{' (confirm)' if t.risky else ''}" for t in self.registry.tools.values()
            )
        elif cmd == "/compact":
            self.run_worker(self.compact())
            return "compacting..."
        else:
            return f"unknown command: {cmd!r}, type /help"
