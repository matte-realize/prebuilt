from eval.figures.headline import curves, draw


def _rows():
    rows = []
    for seed in range(3):
        for r in (1, 2):
            for site in ("resin", "pla"):
                for arm, base in (("isolated", 0.020), ("networked", 0.017), ("oracle", 0.016)):
                    rows.append({"seed": seed, "round": r, "site": site, "arm": arm, "n_train": 16 + 6 * r,
                                 "mae": base / r + 0.001 * seed, "mae_truth": base / r})
    return rows


def test_headline_curves_and_files(tmp_path):
    sim, diff = curves(_rows(), "mae")
    assert sim[1]["isolated"][0] == 22 and round(float(diff[1].mean()), 6) == 0.003
    out = tmp_path / "h.png"
    draw(_rows(), _rows(), "mae", str(out), prereg=None)
    assert out.stat().st_size > 10_000 and out.with_suffix(".pdf").exists()
