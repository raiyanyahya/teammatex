"""Tests for GitHub PR ingestion (app.services.integrations.pr_sync).

PRs live in the GitHub API, not in the cloned git repo, so onboarding never
captured them and every repo showed 0 open PRs. These tests pin the parsing,
pagination, and DB-reconcile behaviour of the sync that fixes that.
"""

from sqlalchemy import select

from app.models.pr import PR
from app.models.repo import Repo
from app.services.integrations import pr_sync


def test_owner_repo_parses_clone_url():
    assert (
        pr_sync.owner_repo("https://github.com/charmbracelet/bubbletea.git")
        == "charmbracelet/bubbletea"
    )


def test_owner_repo_parses_web_url():
    assert pr_sync.owner_repo("https://github.com/charmbracelet/crush") == "charmbracelet/crush"


def test_owner_repo_rejects_org_only_url():
    assert pr_sync.owner_repo("https://github.com/charmbracelet") is None


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class _FakeClient:
    """Returns successive pages, then an empty page — mimics GitHub pagination."""

    def __init__(self, pages):
        self._pages = pages
        self.calls = []

    def get(self, url, params=None):
        self.calls.append((url, params))
        page = (params or {}).get("page", 1)
        idx = page - 1
        return _FakeResponse(self._pages[idx] if idx < len(self._pages) else [])


def _pr(number, title="t", ref="branch", created="2020-01-01T00:00:00Z"):
    return {
        "number": number,
        "title": title,
        "head": {"ref": ref},
        "created_at": created,
        "state": "open",
    }


def test_fetch_open_prs_paginates_until_short_page():
    # 100 on page 1 (full → keep going), 5 on page 2 (short → stop).
    client = _FakeClient([[_pr(i) for i in range(100)], [_pr(i) for i in range(100, 105)]])
    prs = pr_sync.fetch_open_prs("charmbracelet/crush", token="t", client=client)
    assert len(prs) == 105
    assert [c[1]["page"] for c in client.calls] == [1, 2]


class _AlwaysFullClient:
    """Every page returns a full 100 items — simulates a misbehaving API that
    never returns a short/empty page, which would loop forever without a cap."""

    def __init__(self):
        self.calls = 0

    def get(self, url, params=None):
        self.calls += 1
        return _FakeResponse([_pr(i) for i in range(100)])


def test_fetch_open_prs_stops_at_max_pages():
    client = _AlwaysFullClient()
    prs = pr_sync.fetch_open_prs("charmbracelet/crush", token="t", client=client)
    # Bounded by the page ceiling, not an infinite loop.
    assert client.calls <= pr_sync.MAX_PAGES
    assert len(prs) == 100 * pr_sync.MAX_PAGES


def _make_repo(db):
    repo = Repo(github_url="https://github.com/charmbracelet/bubbletea.git", local_name="bubbletea")
    db.add(repo)
    db.commit()
    return repo


def test_reconcile_inserts_new_prs_with_github_created_at(db_session):
    repo = _make_repo(db_session)
    gh = [_pr(78, title="fix things", ref="feat/x", created="2021-06-01T12:00:00Z")]

    result = pr_sync.reconcile_prs(db_session, str(repo.id), gh)

    assert result["added"] == 1
    rows = db_session.execute(select(PR).where(PR.repo_id == str(repo.id))).scalars().all()
    assert len(rows) == 1
    assert rows[0].github_pr_number == 78
    assert rows[0].status == "open"
    # created_at must come from GitHub, not "now" — otherwise the standup thinks
    # every historical PR was opened today.
    assert rows[0].created_at.year == 2021


def test_reconcile_is_idempotent(db_session):
    repo = _make_repo(db_session)
    gh = [_pr(1), _pr(2)]
    pr_sync.reconcile_prs(db_session, str(repo.id), gh)
    result = pr_sync.reconcile_prs(db_session, str(repo.id), gh)
    assert result["added"] == 0
    rows = db_session.execute(select(PR).where(PR.repo_id == str(repo.id))).scalars().all()
    assert len(rows) == 2


def test_reconcile_closes_prs_no_longer_open(db_session):
    repo = _make_repo(db_session)
    pr_sync.reconcile_prs(db_session, str(repo.id), [_pr(1), _pr(2)])
    # PR 2 merged/closed on GitHub → only 1 comes back open.
    pr_sync.reconcile_prs(db_session, str(repo.id), [_pr(1)])
    rows = {
        p.github_pr_number: p.status
        for p in db_session.execute(select(PR).where(PR.repo_id == str(repo.id))).scalars().all()
    }
    assert rows[1] == "open"
    assert rows[2] == "closed"


def test_reconcile_preserves_agent_created_prs(db_session):
    """A PR the agent opened (task_id set) must not be auto-closed just because
    it isn't in the externally-fetched open-PR snapshot."""
    repo = _make_repo(db_session)
    agent_pr = PR(
        repo_id=str(repo.id),
        github_pr_number=999,
        title="agent pr",
        branch="teammatex/x",
        status="open",
        task_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )
    db_session.add(agent_pr)
    db_session.commit()

    # External sync returns no open PRs at all.
    pr_sync.reconcile_prs(db_session, str(repo.id), [])

    refreshed = db_session.execute(select(PR).where(PR.github_pr_number == 999)).scalar_one()
    assert refreshed.status == "open"
