import plotly.graph_objects as go
import streamlit as st

from f1analytics import config
from f1analytics.analysis.undercut import undercut_margin
from f1analytics.ui import charts


def render(ctx):
    st.subheader("Undercut calculator (quick, no randomness)")
    st.caption("Undercut = you pit first, use fresh tyres to go faster, and come out ahead when your rival pits later.")
    c1, c2, c3 = st.columns(3)
    gap = c1.number_input("Gap to the car ahead (s)", value=3.2, step=0.1, key="uc_gap")
    pit_loss = c1.number_input("Your pit-lane time loss (s)", value=config.DEFAULT_PIT_LOSS_S, step=0.5, key="uc_pa")
    pit_target = c1.number_input("Rival's pit-lane time loss (s)", value=config.DEFAULT_PIT_LOSS_S, step=0.5, key="uc_pt")
    fresh = c2.number_input("Fresh-tyre advantage, first lap (s)", value=1.4, step=0.1, key="uc_fresh")
    k = c2.slider("Laps the rival stays out after you pit", 1, 3, 1, key="uc_k")
    warm = c2.number_input("Out-lap warm-up penalty (s, est.)", value=config.WARMUP_PENALTY_S, step=0.1, key="uc_w")
    deg_old = c3.number_input("Rival's old-tyre wear (s/lap)", value=0.08, step=0.01, format="%.3f", key="uc_do")
    deg_new = c3.number_input("Your new-tyre wear (s/lap)", value=0.05, step=0.01, format="%.3f", key="uc_dn")
    traffic = c3.text_input("Gaps to cars behind you (s, comma-separated)", "", key="uc_field",
                            help="Leave empty to ignore traffic. Example: 1.5, 4, 7.5, 12, 18, 21.5")
    field = _parse(traffic)
    r = undercut_margin(gap, pit_loss, fresh, k, pit_target, deg_old, deg_new, warm, field_gaps=field)
    if r.success:
        st.success(f"Undercut works: you come out **{-r.final_gap:.2f} s ahead**.")
    else:
        st.warning(f"Undercut fails: you are still **{r.final_gap:.2f} s behind**.")
    if r.stuck_in_traffic:
        st.info(f"You rejoin only {r.rejoin_gap:.1f} s behind another car, so traffic costs time.")
    terms = list(r.breakdown.items())
    fig = go.Figure(go.Waterfall(
        x=[t for t, _ in terms] + ["Final gap"], y=[v for _, v in terms] + [r.final_gap],
        measure=["absolute"] + ["relative"] * (len(terms) - 1) + ["total"],
        text=[f"{v:+.2f}" for _, v in terms] + [f"{r.final_gap:+.2f}"], textposition="outside",
        increasing=dict(marker=dict(color="#E8524A")), decreasing=dict(marker=dict(color="#3DBE7A")),
        totals=dict(marker=dict(color="#2E9BF0")),
    ))
    st.plotly_chart(charts.style(fig, "How the gap changes (below 0 = you are ahead)", None, "Seconds", 420), key="uc_fig")
    st.caption(
        "Fixes vs the original doc: it now counts pit loss for both cars, your out-lap, every lap the rival stays out "
        "(with their tyres still wearing), the rival's own out-lap and traffic when you rejoin."
    )


def _parse(text):
    out = []
    for part in text.replace(";", ",").split(","):
        try:
            out.append(float(part))
        except ValueError:
            continue
    return tuple(g for g in out if g > 0)
