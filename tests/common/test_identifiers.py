from uuid import UUID

from sayra.common.identifiers import IdType, new_id


def test_new_id_without_type_remains_a_uuid() -> None:
    identifier = new_id()

    assert str(UUID(identifier)) == identifier


def test_new_id_prefixes_uuid_with_resource_type() -> None:
    for id_type in IdType:
        prefix = f"{id_type.value}_"
        identifier = new_id(id_type)

        assert identifier.startswith(prefix)
        uuid_part = identifier.removeprefix(prefix)
        assert str(UUID(uuid_part)) == uuid_part
        assert len(identifier) <= 64
