from slugify import slugify

assert slugify("Hello, World!") == "hello-world"
assert slugify("  Multiple   spaces -- and dashes  ") == "multiple-spaces-and-dashes"
assert slugify("Ünïcödé café") == "n-c-d-caf"
assert slugify("already-a-slug") == "already-a-slug"
assert slugify("abcdefghij" * 10, max_length=25) == "abcdefghijabcdefghijabcde"
assert slugify("cut-here-please", max_length=9) == "cut-here"
assert slugify("!!!") == ""
assert slugify("") == ""
print("ok")
