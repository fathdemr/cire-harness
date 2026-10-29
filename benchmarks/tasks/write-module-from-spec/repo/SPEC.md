# slugify

Create `slugify.py` exposing one function:

    slugify(text: str, max_length: int = 50) -> str

Rules, applied in this order:

1. Lowercase the text.
2. Replace every run of characters that are not ASCII letters or digits with a single hyphen.
3. Strip leading and trailing hyphens.
4. If the result is longer than `max_length`, cut it to `max_length` characters and strip trailing hyphens again.
5. An empty result is returned as the empty string.
