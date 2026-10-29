from pydantic import BaseModel, Field

from cire_harness.providers.types import Usage


class TaskSpec(BaseModel):
    goal: str
    files: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance: list[str] = Field(default_factory=list)
    max_turns: int = Field(default=15, ge=5, le=50)

    def render(self) -> str:
        lines = [f"Goal: {self.goal}"]
        lines.append("Files you may change: " + (", ".join(self.files) if self.files else "any"))
        if self.constraints:
            lines.append("Constraints:\n" + "\n".join(f"- {c}" for c in self.constraints))
        if self.acceptance:
            lines.append(
                "Acceptance commands the harness will run after you finish:\n"
                + "\n".join(f"- {c}" for c in self.acceptance)
            )
        return "\n".join(lines)


class Report(BaseModel):
    ok: bool
    attempts: int
    touched: list[str]
    summary: str
    verification: str
    usage: Usage

    def render(self) -> str:
        return (
            f"status: {'ok' if self.ok else 'FAILED'} after {self.attempts} attempt(s)\n"
            f"files touched: {', '.join(self.touched) or 'none'}\n"
            f"executor report: {self.summary.strip() or '(empty)'}\n"
            f"verification:\n{self.verification}"
        )
