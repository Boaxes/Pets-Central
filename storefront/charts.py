"""Bar charts drawn as SVG on the server: no chart library and no JavaScript. Hovering a bar shows its value."""

from dataclasses import dataclass


@dataclass
class Bar:
    x: float
    y: float
    width: float
    height: float
    label: str
    value_text: str
    show_label: bool
    text_x: float = 0  # Where this bar's text goes.
    text_y: float = 0


def column_chart(points, *, width=560, height=200, label_every=1, money=True):
    """Vertical bars for (label, value) points, oldest first, such as revenue by month."""
    if not points:
        return None
    top = max(value for _, value in points) or 1
    plot_height = height - 24  # Room for the labels underneath.
    step = width / len(points)
    bars = []
    for i, (label, value) in enumerate(points):
        bar_height = plot_height * value / top
        bars.append(Bar(x=i * step + step * 0.15, y=plot_height - bar_height, width=step * 0.7, height=bar_height,
                        label=label, value_text=_fmt(value, money),
                        show_label=(len(points) - 1 - i) % label_every == 0,
                        text_x=i * step + step / 2, text_y=height - 6))
    # The view box is a little wider than the bars, so the last label isn't cut off.
    return {'bars': bars, 'width': width, 'view_width': width + 24, 'height': height, 'plot_height': plot_height,
            'top': _fmt(top, money)}


def bar_chart(points, *, width=560, row=26, label_width=170, money=True):
    """Horizontal bars for (label, value) points, largest first, such as sales by department."""
    if not points:
        return None
    top = max(value for _, value in points) or 1
    plot_width = width - label_width - 90  # Room for the value after each bar.
    bars = []
    for i, (label, value) in enumerate(points):
        bar_width = max(plot_width * value / top, 1)
        bars.append(Bar(x=label_width, y=i * row + 4, width=bar_width, height=row - 8, label=label,
                        value_text=_fmt(value, money), show_label=True,
                        text_x=label_width + bar_width + 6, text_y=i * row + 17))
    return {'bars': bars, 'width': width, 'height': row * len(points), 'label_x': label_width - 8}


def _fmt(value, money):
    return f'${value:,.0f}' if money else f'{value:,.0f}'
