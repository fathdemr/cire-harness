from cire_harness.tools import coerce, schema

SCHEMA = schema(
    n={"type": "integer"},
    x={"type": "number"},
    flag={"type": "boolean"},
    name={"type": "string"},
)


def test_strings_are_converted_to_schema_types():
    args = {"n": "5000", "x": "0.5", "flag": "false", "name": "7"}
    assert coerce(SCHEMA, args) == {"n": 5000, "x": 0.5, "flag": False, "name": "7"}


def test_bad_or_unknown_values_are_left_alone():
    args = {"n": "abc", "flag": "maybe", "extra": "1", "already": 3}
    assert coerce(SCHEMA, args) == args
    assert coerce({}, args) == args
