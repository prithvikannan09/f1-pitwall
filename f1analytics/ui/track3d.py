import numpy as np
import plotly.graph_objects as go

Z_SCALE = 4.0
STEP_S = 0.5


def frames_data(cmp, step=STEP_S):
    """Car positions and the time gap every `step` seconds through the lap, from a duel.compare table."""
    f = cmp["f"].to_numpy(float)
    ta, tb = cmp["t_a"].to_numpy(float), cmp["t_b"].to_numpy(float)
    end = float(max(ta[-1], tb[-1]))
    times = np.arange(0.0, end + step, step)
    fa = np.interp(times, ta, f)
    fb = np.interp(times, tb, f)
    gap = np.interp(fa, f, tb) - times
    return times, fa, fb, gap


def _xyz(cmp, frac):
    f = cmp["f"].to_numpy(float)
    x = np.interp(frac, f, cmp["x"].to_numpy(float))
    y = np.interp(frac, f, cmp["y"].to_numpy(float))
    z = np.interp(frac, f, cmp["z"].to_numpy(float)) if "z" in cmp else np.zeros_like(np.atleast_1d(frac), dtype=float)
    return x, y, z


def lap_3d(cmp, ca, cb, col_a, col_b, height=460):
    if "x" not in cmp:
        return None
    z0 = cmp["z"].min() if "z" in cmp else 0.0
    zz = ((cmp["z"] - z0) * Z_SCALE) if "z" in cmp else cmp["x"] * 0
    dv = (cmp["v_b"] - cmp["v_a"]).clip(-25, 25)
    times, fa, fb, gap = frames_data(cmp)
    xa, ya, za = _xyz(cmp, fa)
    xb, yb, zb = _xyz(cmp, fb)
    za, zb = (za - z0) * Z_SCALE, (zb - z0) * Z_SCALE
    track = go.Scatter3d(x=cmp["x"], y=cmp["y"], z=zz, mode="lines", name="Track",
                         line=dict(width=9, color=dv, colorscale=[[0, col_a], [0.5, "#55556A"], [1, col_b]], cmin=-25, cmax=25),
                         customdata=np.stack([cmp["m"], cmp["v_a"], cmp["v_b"]], axis=1),
                         hovertemplate=f"%{{customdata[0]:.0f}} m · {ca} %{{customdata[1]:.0f}} · {cb} %{{customdata[2]:.0f}} km/h<extra></extra>",
                         showlegend=False)

    def car(x, y, z, colr, who):
        return go.Scatter3d(x=[x], y=[y], z=[z + 12], mode="markers+text", text=[who], textposition="top center",
                            textfont=dict(color="#F3F3F5", size=11), marker=dict(size=7, color=colr, line=dict(color="#FFFFFF", width=2)),
                            name=who, hoverinfo="skip")

    def label(i):
        g = gap[i]
        lead = ca if g >= 0 else cb
        return f"{times[i]:.1f}s · {lead} ahead by {abs(g):.2f}s"

    frames = [go.Frame(data=[car(xa[i], ya[i], za[i], col_a, ca), car(xb[i], yb[i], zb[i], col_b, cb)], traces=[1, 2], name=str(i),
                       layout=go.Layout(title=dict(text=label(i)))) for i in range(len(times))]
    fig = go.Figure(data=[track, car(xa[0], ya[0], za[0], col_a, ca), car(xb[0], yb[0], zb[0], col_b, cb)], frames=frames)
    span = max(float(cmp["x"].max() - cmp["x"].min()), float(cmp["y"].max() - cmp["y"].min()), 1.0)
    fig.update_layout(
        height=height, title=dict(text=label(0), x=0, font=dict(size=12)), showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", font=dict(family="Michroma, sans-serif", color="#F3F3F5", size=10), margin=dict(l=0, r=0, t=40, b=0),
        scene=dict(xaxis=dict(visible=False), yaxis=dict(visible=False), zaxis=dict(visible=False),
                   aspectmode="manual", aspectratio=dict(x=(cmp["x"].max() - cmp["x"].min()) / span, y=(cmp["y"].max() - cmp["y"].min()) / span, z=0.25),
                   camera=dict(eye=dict(x=0.55, y=-0.8, z=0.55)), bgcolor="rgba(0,0,0,0)"),
        updatemenus=[dict(type="buttons", direction="left", x=0, y=0, xanchor="left", yanchor="top", pad=dict(t=6),
                          bgcolor="#232330", bordercolor="#2E2E3A", font=dict(color="#F3F3F5", size=11),
                          buttons=[dict(label="▶ Play", method="animate",
                                        args=[None, dict(frame=dict(duration=int(STEP_S * 1000 / 2), redraw=True), fromcurrent=True, transition=dict(duration=0))]),
                                   dict(label="❚❚ Pause", method="animate", args=[[None], dict(mode="immediate", frame=dict(duration=0, redraw=False))])])],
        sliders=[dict(x=0.3, y=0, len=0.7, pad=dict(t=6), currentvalue=dict(visible=False), bgcolor="#2E2E3A", bordercolor="#2E2E3A",
                      activebgcolor="#E10600", font=dict(color="#A3A3B2", size=9), ticklen=0, minorticklen=0,
                      steps=[dict(method="animate", label=(f"{times[i]:.0f}s" if i % 40 == 0 else ""), args=[[str(i)], dict(mode="immediate", frame=dict(duration=0, redraw=True))])
                             for i in range(0, len(times), 1)])])
    fig._pw_no_tidy = True
    return fig
