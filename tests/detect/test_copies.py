"""A component copy is the same resolved object, not merely equal JSON."""

from tenon.detect import ChangeKind, diff
from tenon.detect.ingest import parse


def parse_spec(schemas: str, paths: str = "paths: {}\n") -> dict:
    return parse(
        f"openapi: 3.1.0\n{paths}components:\n  schemas:\n{schemas}",
        "<inline>",
    )


def user(kind: str) -> str:
    return (
        "    User:\n"
        "      type: object\n"
        "      properties:\n"
        f"        id: {{type: {kind}}}\n"
    )


TWO_USES = """\
paths:
  /users:
    get:
      responses:
        "200":
          description: OK
          content:
            application/json:
              schema: {$ref: '#/components/schemas/User'}
  /admins:
    get:
      responses:
        "200":
          description: OK
          content:
            application/json:
              schema: {$ref: '#/components/schemas/User'}
"""


def test_a_component_used_by_two_paths_is_reported_once():
    old = parse_spec(user("string"), TWO_USES)
    new = parse_spec(user("integer"), TWO_USES)

    changes = diff(old, new).changes

    assert [(change.kind, change.location.pointer) for change in changes] == [
        (ChangeKind.PROPERTY_TYPE_CHANGED, "#/components/schemas/User/properties")
    ]


INLINE = """\
paths:
  /users:
    get:
      responses:
        "200":
          description: OK
          content:
            application/json:
              schema:
                type: object
                properties:
                  id: {type: %s}
"""


def test_an_inline_copy_of_a_component_is_diffed_at_its_location():
    old = parse_spec(user("string"), INLINE % "string")
    new = parse_spec(user("integer"), INLINE % "integer")

    pointers = {change.location.pointer for change in diff(old, new).changes}

    assert pointers == {
        "#/components/schemas/User/properties",
        "#/paths/~1users/get/responses/200/content/application~1json/schema/properties",
    }


ALIAS_PATH = """\
paths:
  /users:
    get:
      responses:
        "200":
          description: OK
          content:
            application/json:
              schema: {$ref: '#/components/schemas/Alias'}
"""


def aliases(kind: str) -> str:
    return (
        "    Base:\n"
        "      type: object\n"
        "      properties:\n"
        f"        value: {{type: {kind}}}\n"
        "    Alias:\n"
        "      $ref: '#/components/schemas/Base'\n"
    )


def test_a_component_ref_to_another_component_shares_its_object_and_skips_the_ref():
    old = parse_spec(aliases("string"), ALIAS_PATH)
    new = parse_spec(aliases("integer"), ALIAS_PATH)

    base = old["components"]["schemas"]["Base"]
    assert old["components"]["schemas"]["Alias"] is base
    assert old["paths"]["/users"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] is base

    changes = diff(old, new).changes
    assert not [
        change for change in changes if change.location.pointer.startswith("#/paths")
    ]
    assert "#/components/schemas/Base/properties" in {
        change.location.pointer for change in changes
    }
