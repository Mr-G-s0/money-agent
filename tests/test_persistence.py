from money_agent.storage import Database


def test_memory_survives_new_database_instance(tmp_path):
    path = tmp_path / "persistent.db"
    first = Database(path)
    first.initialize()
    first.remember("lesson", "Validate demand before spending", {"result": "saved"})

    second = Database(path)
    second.initialize()
    memories = second.memories()

    assert len(memories) == 1
    assert memories[0]["category"] == "lesson"
    assert memories[0]["content"] == "Validate demand before spending"
    assert memories[0]["metadata"] == {"result": "saved"}


def test_initialize_does_not_reset_starting_balance(tmp_path):
    path = tmp_path / "persistent.db"
    Database(path, starting_balance_cents=10_000).initialize()
    changed_config = Database(path, starting_balance_cents=50_000)
    changed_config.initialize()
    with changed_config.connect() as connection:
        value = connection.execute(
            "SELECT value FROM meta WHERE key='starting_balance_cents'"
        ).fetchone()[0]
    assert value == "10000"

