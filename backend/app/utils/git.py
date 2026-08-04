import os
from pathlib import Path

import pygit2


def _auth_callbacks(token: str):
    """Supply the GitHub token as fetch/clone credentials instead of baking it
    into the remote URL. Embedding ``x-access-token:<token>@`` in the URL wrote
    the token in plaintext into every clone's ``.git/config`` — readable by the
    agent's own file tools — so we pass it out-of-band here and leave a clean
    remote URL on disk."""
    if not token:
        return None
    return pygit2.RemoteCallbacks(credentials=pygit2.UserPass("x-access-token", token))


def clone_or_pull(
    url: str, path: str, branch: str = "main", token: str = "", bare: bool = False
) -> pygit2.Repository:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    callbacks = _auth_callbacks(token)

    git_dir = os.path.join(path, ".git") if not bare else path
    if os.path.exists(git_dir if bare else os.path.join(path, ".git")):
        repo = pygit2.Repository(path if bare else os.path.join(path, ".git"))
        _fetch_and_reset(repo, branch, bare, callbacks)
    else:
        if bare:
            repo = pygit2.init_repository(path, bare=True)
            repo.remotes.create("origin", url)
            remote = repo.remotes["origin"]
            remote.fetch(callbacks=callbacks)
            ref = f"refs/remotes/origin/{branch}"
            if ref in repo.references:
                repo.set_head(ref)
        else:
            repo = pygit2.clone_repository(url, path, callbacks=callbacks)
            head = repo.head.shorthand if not repo.head_is_unborn else "main"
            if head != branch:
                try:
                    remote_branch = f"refs/remotes/origin/{branch}"
                    if remote_branch in repo.references:
                        repo.checkout(remote_branch)
                    else:
                        branch = head
                except Exception:
                    branch = head

    return repo


def read_file_from_bare(repo_path: str, file_path: str, ref: str = "HEAD") -> str | None:
    repo = pygit2.Repository(repo_path)
    try:
        commit = repo.revparse_single(ref)
        if isinstance(commit, pygit2.Tag):
            commit = commit.peel(pygit2.Commit)
        tree = commit.tree
        entry = tree[file_path]
        blob = repo[entry.id]
        return blob.data.decode("utf-8", errors="replace")
    except Exception:
        return None


def _fetch_and_reset(
    repo: pygit2.Repository, branch: str, bare: bool = False, callbacks=None
) -> None:
    try:
        remote = repo.remotes["origin"]
    except KeyError:
        return
    remote.fetch(callbacks=callbacks)
    remote_branch = f"refs/remotes/origin/{branch}"
    try:
        if remote_branch in repo.references:
            if bare:
                repo.set_head(remote_branch)
            else:
                repo.checkout(remote_branch)
                repo.reset(repo.lookup_reference(remote_branch).target, pygit2.GIT_RESET_HARD)
    except Exception:
        pass


def create_branch(repo_path: str, branch_name: str, base: str = "main") -> str:
    repo = pygit2.Repository(repo_path)
    base_ref = f"refs/remotes/origin/{base}"
    if base_ref not in repo.references:
        base_ref = f"refs/heads/{base}"
    base_oid = repo.references[base_ref].target
    branch_ref = f"refs/heads/{branch_name}"
    repo.branches.local.create(branch_name, repo[base_oid])
    repo.checkout(branch_ref)
    return branch_ref


def get_repo_path(clone_root: str, local_name: str) -> str:
    return str(Path(clone_root) / local_name)
