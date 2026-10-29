# Contributing

Thanks for your interest. cire-harness is a small project with one maintainer, so the process is light but strict about a few things.

## Before you write code

1. **Open an issue first.** Describe the bug or the change you have in mind. For anything beyond a typo, wait for a maintainer reply before starting; it saves both of us from work that will not be merged.
2. Check the issue is not already open and that the behaviour is not covered in `docs/PLAN.md`.

## Making a change

1. Fork the repository and create a branch named `type/short-topic`, for example `fix/mcp-env-passthrough` or `feat/openai-streaming`.
2. Keep the change small and focused: one logical change per pull request.
3. Run the checks before every commit:

   ```bash
   uv sync
   uv run ruff check .
   uv run pytest
   ```

4. Add or update tests for what you changed. Model calls in tests go through `FakeProvider`, never a real API.
5. Follow the house style: no code comments or docstrings, small typed modules, no new dependencies without a reason stated in the pull request.
6. Commit messages are one short imperative line, no body unless essential, no emoji, no trailers. Model or vendor names do not belong in commit messages.
7. Never commit secrets. Keys are read from environment variables only; the config file holds variable names, never values.

## Pull requests

- Reference the issue (`Closes #12`) and explain what changed and why in a few sentences.
- CI must pass (ruff and pytest).
- Every pull request needs a review and approval from the maintainer before it can be merged. Direct pushes to `main` are not accepted.
- Expect review comments; small follow-up commits on the same branch are fine.

## Reporting a security issue

Do not open a public issue. See [SECURITY.md](SECURITY.md).

## License

By contributing you agree that your contribution is licensed under the MIT License, like the rest of the project.
