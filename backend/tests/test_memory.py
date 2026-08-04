"""Test the memory manager — remember, recall, eviction, preferences."""

import pytest

from app.services.agent.memory import MemoryManager


class TestMemoryManager:
    @pytest.fixture
    def memory(self):
        return MemoryManager()

    def test_remember_and_recall(self, memory):
        memory.remember("key1", "value1", "test")
        item = memory.recall("key1")
        assert item is not None
        assert item.key == "key1"
        assert item.value == "value1"
        assert item.category == "test"

    def test_recall_nonexistent(self, memory):
        item = memory.recall("nonexistent")
        assert item is None

    def test_recall_promotes_to_working(self, memory):
        for i in range(30):
            memory.remember(f"key{i}", f"value{i}", "test", importance=0.3)

        memory.recall("key0")
        item = memory.recall("key0")
        assert item is not None

    def test_working_memory_eviction(self, memory):
        for i in range(30):
            memory.remember(f"key{i}", f"value{i}", "test", importance=0.3)

        assert len(memory.working) <= memory.MAX_WORKING_MEMORY
        assert len(memory.episodic) > 0

    def test_high_importance_promoted(self, memory):
        for i in range(30):
            memory.remember(f"low{i}", f"val{i}", "test", importance=0.3)

        memory.remember("important", "critical", "test", importance=0.9)

        items = memory.recall_recent(limit=5)
        has_important = any(i.key == "important" for i in items)
        assert has_important

    def test_recall_recent_by_category(self, memory):
        memory.remember("a", "1", "task_context")
        memory.remember("b", "2", "feedback")
        memory.remember("c", "3", "task_context")

        task_items = memory.recall_recent(category="task_context")
        assert len(task_items) == 2
        assert all(i.category == "task_context" for i in task_items)

    def test_learn_and_get_preference(self, memory):
        memory.learn_preference("indent_style", "spaces_4")
        pref = memory.get_preference("indent_style")
        assert pref == "spaces_4"

    def test_preference_capped(self, memory):
        for i in range(150):
            memory.learn_preference(f"key{i}", f"value{i}")
        assert len(memory.preferences) <= memory.MAX_PREFERENCES

    def test_learn_convention(self, memory):
        memory.learn_convention("Use async/await for I/O")
        memory.learn_convention("Use type hints everywhere")

        conventions = memory.get_conventions()
        assert "async/await" in conventions
        assert "type hints" in conventions

    def test_convention_deduplication(self, memory):
        memory.learn_convention("Use type hints")
        memory.learn_convention("Use type hints")
        assert len(memory.learned_conventions) == 1

    def test_convention_capped(self, memory):
        for i in range(80):
            memory.learn_convention(f"Rule {i}")
        assert len(memory.learned_conventions) <= memory.MAX_CONVENTIONS

    def test_build_context_prompt(self, memory):
        memory.remember("task_x", "Implement auth", "task_context", 0.8)
        memory.learn_preference("code_style", "black")
        memory.learn_convention("Use async/await")

        prompt = memory.build_context_prompt()
        assert "Implement auth" in prompt
        assert "black" in prompt
        assert "async/await" in prompt

    def test_empty_context_prompt(self, memory):
        prompt = memory.build_context_prompt()
        assert "No team conventions learned yet" in prompt or prompt == ""

    async def test_persist_and_load(self, memory, async_db):
        memory.learn_preference("test_pref", "test_value")
        memory.learn_convention("Test convention")
        memory.remember("test_mem", "memory_value", "test", 0.7)

        await memory.persist_to_db(async_db)

        memory2 = MemoryManager()
        await memory2.load_from_db(async_db)

        assert memory2.get_preference("test_pref") == "test_value"
        assert "Test convention" in memory2.learned_conventions
