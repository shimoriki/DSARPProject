"""The screen that made selection generalise: keep only features consistent across repos."""
from dsarp.dataset.selection import direction_consistent


def test_keeps_consistent_drops_flipping_features():
    rows = []
    # "good" is higher for winners in every repo; "flip" is higher in one repo, lower in another.
    for repo, flip_win in (("a", 9.0), ("b", 1.0), ("c", 9.0)):
        rows.append({"project": repo, "win": 1, "good": 5.0, "flip": flip_win})
        rows.append({"project": repo, "win": 0, "good": 1.0, "flip": 5.0})
    kept = direction_consistent(rows, ["good", "flip"],
                                value=lambda r, f: r[f], label=lambda r: r["win"])
    assert kept == ["good"]


def test_repo_with_one_class_is_ignored_not_counted_as_agreement():
    rows = [{"project": "a", "win": 1, "x": 5.0}, {"project": "a", "win": 0, "x": 1.0},
            {"project": "b", "win": 0, "x": 9.0}]          # b has no winners
    assert direction_consistent(rows, ["x"], lambda r, f: r[f], lambda r: r["win"]) == ["x"]
