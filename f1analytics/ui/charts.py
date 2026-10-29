import plotly.graph_objects as go

from f1analytics import config

PAIR = ("#2E9BF0", "#FF8700")


def compound_color(name):
    return config.COMPOUND_COLORS.get(str(name).upper(), config.COMPOUND_COLORS["UNKNOWN"])


def style(fig, title=None, x=None, y=None, height=420):
    fig.update_layout(
        title=title, height=height, margin=dict(l=10, r=10, t=50 if title else 20, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    if x:
        fig.update_xaxes(title_text=x)
    if y:
        fig.update_yaxes(title_text=y)
    return fig


def empty(message):
    fig = go.Figure()
    fig.add_annotation(text=message, showarrow=False, font=dict(size=14))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return style(fig, height=200)
