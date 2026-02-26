import reflex as rx

from architracker.components.layout import LINE, MUTED, SURFACE, TEXT, tab_button
from architracker.components.tabs import character_tab, metamob_tab, scanner_tab, tracker_tab, trades_tab
from architracker.state import TrackerState


def index() -> rx.Component:
    return rx.box(
        rx.box(
            position="fixed",
            inset="0",
            pointer_events="none",
            opacity="0.09",
            background="repeating-linear-gradient(180deg, rgba(226,232,240,0.28) 0px, rgba(226,232,240,0.28) 1px, transparent 2px, transparent 4px)",
            z_index="0",
        ),
        rx.box(
            rx.vstack(
                rx.hstack(
                    rx.text("ARCHITRACKER", color="#fda4af", font_size="0.78rem", letter_spacing="0.18em", font_family="'Fira Code', monospace"),
                    rx.spacer(),
                    rx.text("Last updated: ", TrackerState.last_updated, color=MUTED, font_size="0.82rem"),
                    width="100%",
                ),
                rx.grid(
                    rx.vstack(
                        rx.box(
                            rx.heading("Control Deck", size="7", color=TEXT),
                            rx.text("Operations, scan, trade, and sync commands.", color=MUTED, font_size="0.9rem"),
                            width="100%",
                        ),
                        rx.vstack(
                            rx.text("Character selector", color=MUTED, font_size="0.82rem"),
                            rx.select(
                                TrackerState.quest_selector_options,
                                value=TrackerState.current_profile_label,
                                on_change=TrackerState.set_profile_from_label,
                                width="100%",
                                background="#18142f",
                                border=f"1px solid {LINE}",
                            ),
                            width="100%",
                            align="start",
                            spacing="1",
                        ),
                        tab_button("Characters", "characters"),
                        tab_button("Scanner", "scanner"),
                        tab_button("Tracker", "tracker"),
                        tab_button("Trades", "trades"),
                        tab_button("Metamob", "metamob"),
                        rx.divider(width="100%"),
                        rx.text("Inventory", color=MUTED, font_size="0.8rem", text_transform="uppercase", letter_spacing="0.08em", width="100%"),
                        rx.hstack(
                            rx.box(rx.text("All", color=MUTED, font_size="0.8rem"), rx.text(TrackerState.totals["all"], color=TEXT, font_weight="700")),
                            rx.box(rx.text("Missing", color=MUTED, font_size="0.8rem"), rx.text(TrackerState.totals["needed"], color="#fda4af", font_weight="700")),
                            rx.box(rx.text("Dupes", color=MUTED, font_size="0.8rem"), rx.text(TrackerState.totals["duplicate"], color="#c4b5fd", font_weight="700")),
                            width="100%",
                            justify="between",
                        ),
                        spacing="3",
                        align="start",
                        width="100%",
                        background=SURFACE,
                        border=f"1px solid {LINE}",
                        border_radius="18px",
                        padding="1rem",
                        box_shadow="0 14px 32px rgba(10,8,20,0.45)",
                    ),
                    rx.box(
                        rx.cond(
                            TrackerState.active_tab == "scanner",
                            scanner_tab(),
                            rx.cond(
                                TrackerState.active_tab == "characters",
                                character_tab(),
                                rx.cond(
                                    TrackerState.active_tab == "tracker",
                                    tracker_tab(),
                                    rx.cond(TrackerState.active_tab == "trades", trades_tab(), metamob_tab()),
                                ),
                            ),
                        ),
                        width="100%",
                    ),
                    columns="320px 1fr",
                    spacing="4",
                    width="100%",
                    align_items="start",
                ),
                max_width="1320px",
                width="100%",
                margin_x="auto",
                padding=["0.8rem", "1rem", "1.2rem"],
                spacing="4",
                position="relative",
                z_index="1",
            ),
            min_height="100vh",
            background=(
                "radial-gradient(820px 460px at 0% 0%, rgba(124,58,237,0.35), transparent 58%), "
                "radial-gradient(940px 560px at 100% 0%, rgba(244,63,94,0.22), transparent 62%), "
                "linear-gradient(152deg, #0F0F23 0%, #171431 52%, #1f1845 100%)"
            ),
            color="#e7eff8",
            font_family="'Fira Sans', 'Avenir Next', 'Segoe UI', sans-serif",
            padding_bottom="2rem",
        ),
    )
