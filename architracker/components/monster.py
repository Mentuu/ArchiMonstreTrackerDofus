import reflex as rx

from architracker.components.layout import LINE, SURFACE, TEXT
from architracker.state import TrackerState


def monster_card(monster: dict) -> rx.Component:
    status = monster["status"]
    qty = monster["qty"]
    return rx.box(
        rx.button(
            "Copy",
            on_click=rx.set_clipboard(monster["name"]),
            position="absolute",
            top="8px",
            right="8px",
            size="1",
            background="rgba(47,30,84,0.9)",
            color=TEXT,
            border=f"1px solid {LINE}",
        ),
        rx.image(
            src=monster["image_url"],
            alt=monster["name"],
            width="96px",
            height="96px",
            object_fit="contain",
            margin_bottom="0.4rem",
            filter=rx.cond(
                status == "needed",
                "grayscale(85%) brightness(70%)",
                rx.cond(status == "validated", "grayscale(85%) brightness(70%)", "none"),
            ),
        ),
        rx.text(monster["name"], font_weight="700", text_align="center"),
        rx.text(
            f"{monster['zone']} -> {monster['souszone']} (Step {monster['step']})",
            color="#9cb2c6",
            font_size="0.8rem",
            text_align="center",
            margin_bottom="0.35rem",
        ),
        rx.text(
            rx.cond(
                status == "triple",
                f"{qty}x",
                rx.cond(
                    status == "duplicate",
                    f"{qty}x",
                    rx.cond(
                        status == "collected",
                        f"Collected ({qty})",
                        rx.cond(status == "validated", "Step validated", "Missing"),
                    ),
                ),
            ),
            color=rx.cond(
                status == "triple",
                "#f9a8d4",
                rx.cond(
                    status == "duplicate",
                    "#c4b5fd",
                    rx.cond(status == "collected", "#22c55e", rx.cond(status == "validated", "#a7f3d0", "#fda4af")),
                ),
            ),
            font_weight="700",
        ),
        rx.hstack(
            rx.button("-", on_click=TrackerState.update_quantity(monster["name"], -1), background="rgba(47,30,84,0.9)"),
            rx.text(qty, min_width="2ch", text_align="center"),
            rx.button("+", on_click=TrackerState.update_quantity(monster["name"], 1), background="rgba(47,30,84,0.9)"),
            spacing="2",
            margin_top="0.4rem",
        ),
        background=SURFACE,
        border=f"1px solid {LINE}",
        border_radius="16px",
        padding="0.75rem",
        position="relative",
        display="flex",
        flex_direction="column",
        align_items="center",
        box_shadow="0 10px 26px rgba(0,0,0,0.28)",
    )
