import reflex as rx

from architracker.state import TrackerState

SURFACE = "rgba(24, 18, 48, 0.72)"
SURFACE_SOFT = "rgba(33, 24, 66, 0.74)"
LINE = "#4c3b7a"
ACCENT = "#7C3AED"
ACCENT_DEEP = "#F43F5E"
TEXT = "#E2E8F0"
MUTED = "#B7B7D6"


def tab_button(label: str, key: str) -> rx.Component:
    return rx.button(
        label,
        on_click=TrackerState.set_active_tab(key),
        background=rx.cond(
            TrackerState.active_tab == key,
            f"linear-gradient(120deg, {ACCENT} 0%, {ACCENT_DEEP} 100%)",
            SURFACE_SOFT,
        ),
        color=rx.cond(TrackerState.active_tab == key, "#052331", TEXT),
        border=f"1px solid {LINE}",
        border_radius="12px",
        padding="0.7rem 0.95rem",
        font_weight="700",
        letter_spacing="0.01em",
        width="100%",
        justify_content="start",
        box_shadow=rx.cond(
            TrackerState.active_tab == key,
            "0 8px 22px rgba(124, 58, 237, 0.35)",
            "0 6px 16px rgba(0, 0, 0, 0.22)",
        ),
    )


def filter_button(label: str, filter_key: str, value_key: str) -> rx.Component:
    return rx.button(
        rx.text(f"{label}: "),
        rx.text(TrackerState.totals[value_key], as_="span"),
        on_click=TrackerState.set_active_filter(filter_key),
        background=rx.cond(
            TrackerState.active_filter == filter_key,
            f"linear-gradient(120deg, {ACCENT} 0%, {ACCENT_DEEP} 100%)",
            SURFACE_SOFT,
        ),
        color=rx.cond(TrackerState.active_filter == filter_key, "#052331", TEXT),
        border=f"1px solid {LINE}",
        border_radius="10px",
        font_weight="700",
        box_shadow="0 4px 12px rgba(0,0,0,0.18)",
    )


def step_button(step: int) -> rx.Component:
    return rx.button(
        f"Step {step}",
        on_click=TrackerState.set_active_step(step),
        background=rx.cond(
            TrackerState.active_step == step,
            f"linear-gradient(120deg, {ACCENT} 0%, {ACCENT_DEEP} 100%)",
            SURFACE_SOFT,
        ),
        color=rx.cond(TrackerState.active_step == step, "#052331", TEXT),
        border=f"1px solid {LINE}",
        border_radius="10px",
        box_shadow="0 4px 10px rgba(0,0,0,0.2)",
    )
