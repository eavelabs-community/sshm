"""StateManager 持久化测试"""

import json

import pytest


@pytest.fixture
def state_file(tmp_path):
    return tmp_path / ".sshm_state"


@pytest.fixture
def state(state_file):
    from sshm.core.services.storage.state import StateManager

    return StateManager(state_file)


class TestLang:
    def test_default_lang(self, state):
        assert state.read_lang() == "en"

    def test_write_read_lang(self, state):
        state.write_lang("zh")
        assert state.read_lang() == "zh"

    def test_lang_persisted_to_file(self, state, state_file):
        state.write_lang("zh")
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["lang"] == "zh"


class TestAutoAuthor:
    def test_default_true(self, state):
        assert state.read_auto_author() is True

    def test_persist(self, state, state_file):
        state.write_auto_author(False)
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["auto_author"] is False


class TestHostsAuthors:
    def test_hosts(self, state):
        state.write_host("work", "gitlab.com")
        assert state.read_hosts()["work"] == "gitlab.com"

    def test_authors(self, state):
        state.write_author("work", "Alice", "a@x.com")
        assert state.read_authors()["work"]["name"] == "Alice"

    def test_active_keys(self, state):
        state.write_active_key("ed25519", "work")
        assert state.read_active_keys()["ed25519"] == "work"


class TestUpdateDeleteAuthor:
    """author update / delete 命令层行为（隔离 state，不碰真实文件）"""

    @pytest.fixture
    def mgr(self, state):
        from sshm.core.commands.author import AuthorCommands

        class _FakeManager:
            state_manager = state
            had_error = False

            def _fail(self, msg_or_code, *, icon: str = "❌", hint=None, **params):
                self.had_error = True

        m = _FakeManager()
        m.author = AuthorCommands(m)
        return m

    def test_update_keeps_unchanged_field(self, mgr):
        mgr.state_manager.write_author("work", "Alice", "a@x.com")
        mgr.author.update("work", name="Alice2")
        assert mgr.state_manager.read_authors()["work"] == {
            "name": "Alice2",
            "email": "a@x.com",
        }

    def test_update_requires_at_least_one(self, mgr):
        mgr.state_manager.write_author("work", "Alice", "a@x.com")
        mgr.author.update("work")  # 无 name/email
        assert mgr.had_error is True
        assert mgr.state_manager.read_authors()["work"]["name"] == "Alice"

    def test_update_missing_label(self, mgr):
        mgr.author.update("missing", name="X")
        assert mgr.had_error is True

    def test_delete(self, mgr):
        mgr.state_manager.write_author("work", "Alice", "a@x.com")
        mgr.author.remove("work", skip_confirm=True)
        assert "work" not in mgr.state_manager.read_authors()

    def test_delete_missing_label(self, mgr):
        mgr.author.remove("missing", skip_confirm=True)
        assert mgr.had_error is True
