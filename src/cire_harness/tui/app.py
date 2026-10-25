from textual.app import App
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RichLog

from cire_harness.loop.loop import run_agent
from cire_harness.providers.types import Message, ToolCall, Usage
from cire_harness.session import save_session


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
    def __init__(self, provider, registry, messages: list[Message], session_id):
        super().__init__()
        self.provider = provider
        self.registry = registry
        self.messages = messages
        self.session_id = session_id
        self.usage = Usage()

    def compose(self):
        yield RichLog(wrap=True)
        yield Input(placeholder="...")

    def on_mount(self):
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
        )
        save_session(self.session_id, self.messages)
