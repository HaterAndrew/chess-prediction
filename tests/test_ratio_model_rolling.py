"""v5 Cat L (audit/AUDIT_2026-07-30.md): window-engine rolling retrain.

build_ratio_model hard-filtered tournament_year < 2026, so no completed 2026
event could ever inform a 2026 window prediction — while the main engine's
fit() folds completed 2026 tids in. That asymmetry left the window engine's
2026 coverage 27pp below its 2023-25 folds with no correction layer to absorb
the regime shift.

Contract: completed_tids admits exactly those tids alongside the pre-2026
corpus; omitting the parameter reproduces the old behavior byte-for-byte
(window_grading's leak-free folds depend on that).
"""

import pandas as pd


from ratio_model import build_ratio_model  # noqa: E402


def _frames():
    rows, daily_rows = [], []
    for tid, (family, year, final) in enumerate([
        ("Rolling Open", 2024, 100),
        ("Rolling Open", 2025, 110),
        ("Rolling Open", 2026, 120),   # completed 2026 edition
        ("Rolling Open", 2026, 130),   # still-live 2026 edition (not completed)
    ]):
        rows.append({
            "tid": tid, "family": family, "tournament_year": year,
            "final_count": final, "has_timestamps": True,
            "is_covid": False, "is_online": False,
        })
        for T, cum in ((10, 20), (7, 30), (5, 40), (3, 50), (1, 80), (0, final)):
            daily_rows.append({"tid": tid, "T": T, "cum_regs": cum})
    return pd.DataFrame(rows), pd.DataFrame(daily_rows)


def test_completed_tids_admit_2026_ratios():
    summary, daily = _frames()
    ratios = build_ratio_model(summary, daily, completed_tids={2})
    # 2024 + 2025 + the completed 2026 edition contribute at T=3; the
    # still-live 2026 edition stays out.
    assert len(ratios["Rolling Open"][3]) == 3
    assert 120 / 50 in ratios["Rolling Open"][3]
    assert 130 / 50 not in ratios["Rolling Open"][3]


def test_default_behavior_unchanged():
    summary, daily = _frames()
    ratios = build_ratio_model(summary, daily)
    assert len(ratios["Rolling Open"][3]) == 2
    assert all(r in ratios["Rolling Open"][3] for r in (100 / 50, 110 / 50))
    # None is the explicit no-op the 04d call site passes when the set is empty
    ratios_none = build_ratio_model(summary, daily, completed_tids=None)
    assert ratios_none["Rolling Open"][3] == ratios["Rolling Open"][3]
