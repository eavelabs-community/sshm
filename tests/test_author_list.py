"""author list 命令的匹配逻辑测试：联合匹配 + 无匹配提示。

覆盖修复前的 bug：
- 仅邮箱相同但姓名不同的作者不应被误标 📍；
- 当前生效作者的 name+email 组合不在列表中时应提示。
"""

from pathlib import Path

import pytest

from sshm.core.commands.author import AuthorCommands


@pytest.fixture
def repo_dir(tmp_path):
    """构造一个带 .git 的临时仓库目录，使 in_repo 判定为真。"""
    (tmp_path / ".git").mkdir()
    return tmp_path


def _make_author_cmds(manager, repo_dir, local, global_):
    """返回一个 AuthorCommands，并把 git 配置读取替换为给定常量。

    local / global_ 是 (name, email) 元组，None 表示未设置。
    """
    class _FakeService:
        def __init__(self):
            self.git_get_config = lambda repo_path, scope, key: None

    cmds = AuthorCommands(manager)
    cmds.m.author_service = _FakeService()

    def fake_git_get_config(repo_path, scope, key):
        pair = local if scope == "local" else global_
        if pair is None:
            return None
        name, email = pair
        if key == "user.name":
            return name
        return email

    cmds.m.author_service.git_get_config = fake_git_get_config
    return cmds


def _seed_authors(manager, authors):
    for label, name, email in authors:
        manager.state_manager.write_author(label, name, email)


def test_joint_match_marks_correct_author(manager, repo_dir, capsys):
    """生效作者 name+email 同时匹配某条时才标 📍。"""
    _seed_authors(
        manager,
        [
            ("work", "365tools", "365tools@gmail.com"),
            ("alt", "eavelabs", "365tools.t1@gmail.com"),
        ],
    )
    cmds = _make_author_cmds(manager, repo_dir, ("365tools", "365tools.t1@gmail.com"), None)
    cmds.list()
    out = capsys.readouterr().out
    # eavelabs 的邮箱命中但姓名不命中，不应标 📍
    assert "eavelabs" in out
    # 没有任何一条同时匹配 name+email，故不出现 📍
    assert "📍" not in out


def test_no_match_shows_warning(manager, repo_dir, capsys):
    """生效作者组合不在列表中时应给出提示。"""
    _seed_authors(
        manager,
        [
            ("work", "365tools", "365tools@gmail.com"),
            ("alt", "eavelabs", "365tools.t1@gmail.com"),
        ],
    )
    # 生效作者为 365tools <365tools.t1@gmail.com>：name 在 work，email 在 alt，组合不存在
    cmds = _make_author_cmds(manager, repo_dir, ("365tools", "365tools.t1@gmail.com"), None)
    cmds.list()
    out = capsys.readouterr().out
    # 注意：rich 可能折行，故用不跨行的片段断言
    assert "不在已保存列表中" in out or "NOT in the" in out


def test_exact_match_marks_one(manager, repo_dir, capsys):
    """当列表中确有 name+email 完全一致的一条时，应标 📍。"""
    _seed_authors(
        manager,
        [
            ("work", "365tools", "365tools.t1@gmail.com"),
            ("alt", "eavelabs", "365tools.t1@gmail.com"),
        ],
    )
    cmds = _make_author_cmds(manager, repo_dir, ("365tools", "365tools.t1@gmail.com"), None)
    cmds.list()
    out = capsys.readouterr().out
    lines = out.splitlines()
    marked = [ln for ln in lines if "📍" in ln]
    assert len(marked) == 1
    assert "WORK" in marked[0]


def test_add_rejects_duplicate_identity(manager, repo_dir, capsys):
    """新增与已有记录 name+email 完全相同的作者（不同 label）应被拒绝。"""
    _seed_authors(manager, [("work", "365tools", "365tools@gmail.com")])
    cmds = AuthorCommands(manager)
    cmds.add("dup", "365tools", "365tools@gmail.com")
    out = capsys.readouterr().out
    assert "已存在" in out or "already exists" in out
    # 重复记录不应被写入
    remaining = manager.state_manager.read_authors()
    assert "dup" not in remaining
    assert "work" in remaining


def test_add_same_label_is_update(manager, repo_dir, capsys):
    """同 label 再次 add 视为更新，不应报重复身份。"""
    _seed_authors(manager, [("work", "365tools", "365tools@gmail.com")])
    cmds = AuthorCommands(manager)
    cmds.add("work", "365tools", "365tools.t1@gmail.com")
    out = capsys.readouterr().out
    # 同 label 更新不应触发"重复身份"拒绝（under label / 已存在于标签）
    assert "已存在于标签" not in out and "already exists under label" not in out
    updated = manager.state_manager.read_authors()["work"]
    assert updated["email"] == "365tools.t1@gmail.com"


def test_add_new_succeeds(manager, repo_dir, capsys):
    """全新 label + 全新身份应成功写入。"""
    cmds = AuthorCommands(manager)
    cmds.add("fresh", "alice", "alice@example.com")
    out = capsys.readouterr().out
    assert "已保存" in out or "Saved to author list" in out
    assert manager.state_manager.read_authors()["fresh"]["name"] == "alice"
