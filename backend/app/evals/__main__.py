"""Run the retrieval eval and gate on a hit-rate threshold.

    python -m app.evals [--golden fixture.yaml] [--k 3] [--threshold 0.8]

Exits non-zero if hit_rate < threshold, so it can act as a regression gate."""

from __future__ import annotations

import argparse
import asyncio


def exit_code_for(summary: dict, threshold: float) -> int:
    return 0 if summary["hit_rate"] >= threshold else 1


def _print_report(report: dict) -> None:
    print(f"{'ID':<6} {'HIT':<4} {'RANK':<5} QUESTION")
    for it in report["items"]:
        print(
            f"{it['id']:<6} {'YES' if it['hit'] else '-':<4} {str(it['rank'] or '-'):<5} {it['question']}"
        )
    s = report["summary"]
    print(f"\n{s['count']} questions | hit-rate: {s['hit_rate']:.2f} | MRR: {s['mrr']:.2f}")


async def _amain(args: argparse.Namespace) -> int:
    from pathlib import Path

    # Import the module, not the name: async_session_factory is None until
    # _init_engine() runs, so a `from ... import async_session_factory` would
    # capture None. Access it via the module after init.
    import app.db.session as _session
    from app.evals.engine import run_eval
    from app.evals.fixtures import load_fixture_repo, load_golden
    from app.services.knowledge.embeddings import EmbeddingService

    _session._init_engine()
    embedder = EmbeddingService()
    golden = load_golden(args.golden)
    async with _session.async_session_factory() as db:
        if args.golden == "fixture.yaml":
            fixture_dir = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "eval_repo"
            await load_fixture_repo(db, embedder, fixture_dir, "eval-fixture")
        report = await run_eval(db, embedder, golden, k=args.k)
    _print_report(report)
    return exit_code_for(report["summary"], args.threshold)


def main() -> None:
    p = argparse.ArgumentParser(prog="python -m app.evals")
    p.add_argument("--golden", default="fixture.yaml")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--threshold", type=float, default=0.8)
    args = p.parse_args()
    raise SystemExit(asyncio.run(_amain(args)))


if __name__ == "__main__":
    main()
