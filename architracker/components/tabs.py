import reflex as rx

from architracker.components.layout import ACCENT, ACCENT_DEEP, LINE, MUTED, SURFACE, SURFACE_SOFT, TEXT, filter_button, step_button
from architracker.components.monster import monster_card
from architracker.state import TrackerState


def section_card(title: str, subtitle: str, *children: rx.Component) -> rx.Component:
    return rx.box(
        rx.vstack(
            rx.text(title, color=TEXT, font_weight="700", font_size="0.98rem"),
            rx.text(subtitle, color=MUTED, font_size="0.84rem"),
            *children,
            width="100%",
            align="start",
            spacing="3",
        ),
        width="100%",
        background=SURFACE_SOFT,
        border=f"1px solid {LINE}",
        border_radius="14px",
        padding="1rem",
    )


def scanner_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("Scanner", font_weight="700", font_size="1.15rem", color=TEXT),
            rx.badge(rx.cond(TrackerState.scanner_mode == "pack", "PACK", "SCAN"), color_scheme="purple"),
            width="100%",
            justify="between",
        ),
        section_card(
            "Mode Selection",
            "Pick the scanner workflow before launch.",
            rx.hstack(
                rx.box(
                    rx.text("Scan", color=TEXT, font_weight="600", font_size="0.88rem"),
                    rx.text("Standard full archimonster scan flow.", color=MUTED, font_size="0.8rem"),
                    background=rx.cond(TrackerState.scanner_mode == "scan", "rgba(124,58,237,0.2)", "transparent"),
                    border=f"1px solid {LINE}",
                    border_radius="10px",
                    padding="0.65rem 0.75rem",
                    width="100%",
                    cursor="pointer",
                    transition="all 180ms ease",
                    on_click=TrackerState.set_scanner_mode("scan"),
                ),
                rx.box(
                    rx.text("Pack", color=TEXT, font_weight="600", font_size="0.88rem"),
                    rx.text("Same engine, pack workflow enabled directly at launch.", color=MUTED, font_size="0.8rem"),
                    background=rx.cond(TrackerState.scanner_mode == "pack", "rgba(124,58,237,0.2)", "transparent"),
                    border=f"1px solid {LINE}",
                    border_radius="10px",
                    padding="0.65rem 0.75rem",
                    width="100%",
                    cursor="pointer",
                    transition="all 180ms ease",
                    on_click=TrackerState.set_scanner_mode("pack"),
                ),
                spacing="3",
                width="100%",
                align="stretch",
                wrap="wrap",
            ),
        ),
        section_card(
            "Controls",
            "Launch, stop, and refresh scanner process status.",
            rx.hstack(
                rx.button(
                    rx.cond(TrackerState.scanner_mode == "pack", "Start Pack Runner", "Start Archi Scan"),
                    on_click=TrackerState.start_scanner,
                    background=f"linear-gradient(120deg, {ACCENT} 0%, {ACCENT_DEEP} 100%)",
                    color="#021018",
                ),
                rx.button("Stop Scanner", on_click=TrackerState.stop_scan, background=SURFACE, border=f"1px solid {LINE}"),
                rx.button("Refresh Status", on_click=TrackerState.refresh_scan_status, background=SURFACE, border=f"1px solid {LINE}"),
                wrap="wrap",
                spacing="3",
                width="100%",
            ),
            rx.box(
                rx.vstack(
                    rx.hstack(
                        rx.badge(
                            rx.cond(
                                TrackerState.scan_status_tone == "running",
                                "RUNNING",
                                rx.cond(
                                    TrackerState.scan_status_tone == "error",
                                    "ERROR",
                                    rx.cond(TrackerState.scan_status_tone == "warning", "NOTICE", "IDLE"),
                                ),
                            ),
                            color_scheme=rx.cond(
                                TrackerState.scan_status_tone == "running",
                                "green",
                                rx.cond(
                                    TrackerState.scan_status_tone == "error",
                                    "red",
                                    rx.cond(TrackerState.scan_status_tone == "warning", "amber", "gray"),
                                ),
                            ),
                        ),
                        rx.cond(
                            TrackerState.scan_status_updated_at == "",
                            rx.text("No updates yet", color=MUTED, font_size="0.78rem"),
                            rx.hstack(
                                rx.text("Updated at", color=MUTED, font_size="0.78rem"),
                                rx.text(TrackerState.scan_status_updated_at, color="#c4b5fd", font_size="0.78rem"),
                                spacing="1",
                            ),
                        ),
                        width="100%",
                        justify="between",
                        align="center",
                    ),
                    rx.text(
                        TrackerState.tool_status,
                        color=TEXT,
                        font_size="0.9rem",
                        font_family="'Fira Code', monospace",
                        line_height="1.45",
                    ),
                    width="100%",
                    align="start",
                    spacing="2",
                ),
                width="100%",
                background=SURFACE,
                border=f"1px solid {LINE}",
                border_radius="12px",
                padding="0.75rem",
            ),
        ),
        section_card(
            "How The Scan Works",
            "Quick runbook and keyboard shortcuts.",
            rx.text("1. Click start to launch the scanner process.", color=MUTED, font_size="0.88rem"),
            rx.text("2. Keep Dofus visible, hover the search bar, then press F8 once.", color=MUTED, font_size="0.88rem"),
            rx.text("3. Scanner cycles names and saves directly into the selected character profile.", color=MUTED, font_size="0.88rem"),
            rx.text("4. Press F10 to pause or resume the scan loop.", color=MUTED, font_size="0.88rem")
        ),
        width="100%",
        spacing="4",
        background=SURFACE,
        border=f"1px solid {LINE}",
        border_radius="16px",
        padding="1.1rem",
        box_shadow="0 10px 26px rgba(0,0,0,0.28)",
    )


def character_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("Characters", font_weight="700", font_size="1.15rem", color=TEXT),
            rx.badge("Quest Source", color_scheme="purple"),
            width="100%",
            justify="between",
        ),
        section_card(
            "New Character",
            "Only server and character name are needed.",
            rx.hstack(
                rx.vstack(
                    rx.text("Server", color=MUTED, font_size="0.84rem"),
                    rx.select(
                        TrackerState.new_character_server_options,
                        value=TrackerState.new_character_server,
                        on_change=TrackerState.set_new_character_server,
                        width="230px",
                        background=SURFACE,
                        border=f"1px solid {LINE}",
                    ),
                    align="start",
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Character name", color=MUTED, font_size="0.84rem"),
                    rx.input(
                        placeholder="Ex: MonPerso",
                        value=TrackerState.new_character_name,
                        on_change=TrackerState.set_new_character_name,
                        width="360px",
                        background=SURFACE,
                        border=f"1px solid {LINE}",
                    ),
                    align="start",
                    spacing="1",
                ),
                rx.button(
                    "Create character",
                    on_click=TrackerState.add_character,
                    background=f"linear-gradient(120deg, {ACCENT} 0%, {ACCENT_DEEP} 100%)",
                    color="#021018",
                ),
                width="100%",
                wrap="wrap",
                align="end",
                spacing="3",
            ),
            rx.cond(
                TrackerState.character_status != "",
                rx.text(TrackerState.character_status, color=MUTED, font_size="0.85rem"),
            ),
        ),
        section_card(
            "Registered Characters",
            "These entries feed the quest selector and scan assignment menus.",
            rx.grid(
                rx.foreach(
                    TrackerState.character_cards,
                    lambda char: rx.box(
                        rx.vstack(
                            rx.text(char["name"], color=TEXT, font_weight="700"),
                            rx.text(char["server"], color=MUTED, font_size="0.82rem"),
                            rx.text(char["id"], color="#c4b5fd", font_size="0.78rem", font_family="'Fira Code', monospace"),
                            rx.hstack(
                                rx.button(
                                    "Use",
                                    on_click=TrackerState.set_profile(char["id"]),
                                    background=SURFACE,
                                    border=f"1px solid {LINE}",
                                    color=TEXT,
                                ),
                                rx.button(
                                    "Remove",
                                    on_click=TrackerState.remove_character(char["id"]),
                                    background="#2a1721",
                                    border="1px solid #5c2338",
                                    color="#fecdd3",
                                ),
                                width="100%",
                                wrap="wrap",
                            ),
                            spacing="2",
                            align="start",
                            width="100%",
                        ),
                        width="100%",
                        background=SURFACE,
                        border=f"1px solid {LINE}",
                        border_radius="12px",
                        padding="0.8rem",
                    ),
                ),
                columns="repeat(auto-fill, minmax(220px, 1fr))",
                spacing="3",
                width="100%",
            ),
        ),
        width="100%",
        spacing="4",
        background=SURFACE,
        border=f"1px solid {LINE}",
        border_radius="16px",
        padding="1.1rem",
        box_shadow="0 10px 26px rgba(0,0,0,0.28)",
    )


def tracker_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.button("Reset Filters", on_click=TrackerState.reset_filters, background=SURFACE_SOFT, border=f"1px solid {LINE}", color=TEXT),
            justify="start",
            width="100%",
            wrap="wrap",
        ),
        rx.hstack(
            rx.button(
                "All steps",
                on_click=TrackerState.set_active_step(0),
                background=rx.cond(TrackerState.active_step == 0, f"linear-gradient(120deg, {ACCENT} 0%, {ACCENT_DEEP} 100%)", SURFACE_SOFT),
            ),
            rx.foreach(TrackerState.steps, step_button),
            wrap="wrap",
            width="100%",
        ),
        rx.hstack(
            rx.button("Validate active step", on_click=TrackerState.validate_active_step, background=SURFACE_SOFT, border=f"1px solid {LINE}", color=TEXT),
            rx.button("Unvalidate active step", on_click=TrackerState.unvalidate_active_step, background=SURFACE_SOFT, border=f"1px solid {LINE}", color=TEXT),
            rx.text(TrackerState.validated_steps_label, color=MUTED),
            wrap="wrap",
            width="100%",
        ),
        rx.hstack(
            filter_button("All", "all", "all"),
            filter_button("Missing", "needed", "needed"),
            filter_button("Collected", "collected", "collected"),
            filter_button("Dupes", "duplicate", "duplicate"),
            filter_button("Triples+", "triple", "triple"),
            wrap="wrap",
            width="100%",
        ),
        rx.hstack(
            rx.vstack(
                rx.text("Search", color=MUTED, font_size="0.85rem"),
                rx.input(
                    placeholder="Search archimonsters...",
                    value=TrackerState.search_query,
                    on_change=TrackerState.set_search_query,
                    width="340px",
                    background=SURFACE_SOFT,
                    border=f"1px solid {LINE}",
                ),
                align="start",
                spacing="1",
            ),
            rx.vstack(
                rx.text("Sous-zone", color=MUTED, font_size="0.85rem"),
                rx.select(
                    TrackerState.souszone_options,
                    value=TrackerState.active_souszone,
                    on_change=TrackerState.set_active_souszone,
                    width="320px",
                    background=SURFACE_SOFT,
                    border=f"1px solid {LINE}",
                ),
                align="start",
                spacing="1",
            ),
            wrap="wrap",
            width="100%",
        ),
        rx.grid(
            rx.foreach(TrackerState.filtered_monsters, monster_card),
            columns="repeat(auto-fill, minmax(240px, 1fr))",
            spacing="3",
            width="100%",
        ),
        spacing="3",
        width="100%",
        background=SURFACE,
        border=f"1px solid {LINE}",
        border_radius="16px",
        padding="1rem",
        box_shadow="0 10px 26px rgba(0,0,0,0.28)",
    )


def trades_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.vstack(
                rx.text("Trades Assistant", font_weight="700", font_size="1.15rem", color=TEXT),
                rx.text("Compare players, pick matches, and generate a clean trade message.", color=MUTED, font_size="0.84rem"),
                spacing="1",
                align="start",
            ),
            rx.spacer(),
            rx.badge("Load -> Compare -> Select -> Send", color_scheme="purple"),
            width="100%",
        ),
        section_card(
            "Compare With Another Player",
            "Load and normalize both lists before running comparison.",
            rx.hstack(
                rx.vstack(
                    rx.text("Opponent pseudo", color=MUTED, font_size="0.85rem"),
                    rx.input(
                        placeholder="Opponent Metamob pseudo",
                        value=TrackerState.other_pseudo,
                        on_change=TrackerState.set_other_pseudo,
                        width="320px",
                        background=SURFACE,
                        border=f"1px solid {LINE}",
                    ),
                    align="start",
                    spacing="1",
                ),
                rx.vstack(
                    rx.text("Offer mode", color=MUTED, font_size="0.85rem"),
                    rx.select(
                        ["dup", "x3"],
                        value=TrackerState.trade_offer_mode,
                        on_change=TrackerState.set_trade_offer_mode,
                        width="130px",
                        background=SURFACE,
                        border=f"1px solid {LINE}",
                    ),
                    align="start",
                    spacing="1",
                ),
                rx.button(
                    "Load via API",
                    on_click=TrackerState.load_other_player,
                    background=SURFACE,
                    border=f"1px solid {LINE}",
                    color=TEXT,
                ),
                rx.button(
                    "Compare",
                    on_click=TrackerState.run_trade_compare,
                    background=f"linear-gradient(120deg, {ACCENT} 0%, {ACCENT_DEEP} 100%)",
                    color="#021018",
                ),
                wrap="wrap",
                spacing="3",
                width="100%",
                align="end",
            ),
            rx.grid(
                rx.box(
                    rx.vstack(
                        rx.text("Opponent wants", color=MUTED, font_size="0.84rem"),
                        rx.text_area(
                            value=TrackerState.other_wants_text,
                            on_change=TrackerState.set_other_wants_text,
                            min_height="220px",
                            background=SURFACE,
                            border=f"1px solid {LINE}",
                            font_family="'Fira Code', monospace",
                        ),
                        width="100%",
                        align="start",
                        spacing="2",
                    ),
                    background="rgba(15,15,35,0.35)",
                    border=f"1px solid {LINE}",
                    border_radius="12px",
                    padding="0.7rem",
                    width="100%",
                ),
                rx.box(
                    rx.vstack(
                        rx.text("Opponent offers", color=MUTED, font_size="0.84rem"),
                        rx.text_area(
                            value=TrackerState.other_offers_text,
                            on_change=TrackerState.set_other_offers_text,
                            min_height="220px",
                            background=SURFACE,
                            border=f"1px solid {LINE}",
                            font_family="'Fira Code', monospace",
                        ),
                        width="100%",
                        align="start",
                        spacing="2",
                    ),
                    background="rgba(15,15,35,0.35)",
                    border=f"1px solid {LINE}",
                    border_radius="12px",
                    padding="0.7rem",
                    width="100%",
                ),
                columns="repeat(auto-fit, minmax(320px, 1fr))",
                width="100%",
                spacing="3",
            ),
        ),
        section_card(
            "Match Picks",
            "Select what you can give and what you want to receive.",
            rx.grid(
                rx.box(
                    rx.vstack(
                        rx.hstack(
                            rx.text("I can give", color=TEXT, font_size="0.9rem", font_weight="700"),
                            rx.spacer(),
                            rx.badge("Give", color_scheme="amber"),
                            width="100%",
                        ),
                        rx.box(
                            rx.vstack(
                                rx.foreach(
                                    TrackerState.compare_give,
                                    lambda name: rx.button(
                                        name,
                                        on_click=TrackerState.toggle_select_give(name),
                                        background=rx.cond(TrackerState.selected_give.contains(name), "#f59e0b", SURFACE),
                                        color=rx.cond(TrackerState.selected_give.contains(name), "#101010", "#dceaf7"),
                                        border=f"1px solid {LINE}",
                                        border_radius="10px",
                                        transition="all 160ms ease",
                                        width="100%",
                                        justify_content="start",
                                    ),
                                ),
                                width="100%",
                                spacing="2",
                                align="start",
                            ),
                            max_height="260px",
                            overflow_y="auto",
                            width="100%",
                        ),
                        width="100%",
                        spacing="2",
                        align="start",
                    ),
                    background="rgba(15,15,35,0.35)",
                    border=f"1px solid {LINE}",
                    border_radius="12px",
                    padding="0.7rem",
                    width="100%",
                ),
                rx.box(
                    rx.vstack(
                        rx.hstack(
                            rx.text("I can receive", color=TEXT, font_size="0.9rem", font_weight="700"),
                            rx.spacer(),
                            rx.badge("Receive", color_scheme="violet"),
                            width="100%",
                        ),
                        rx.box(
                            rx.vstack(
                                rx.foreach(
                                    TrackerState.compare_receive,
                                    lambda name: rx.button(
                                        name,
                                        on_click=TrackerState.toggle_select_receive(name),
                                        background=rx.cond(TrackerState.selected_receive.contains(name), "#f59e0b", SURFACE),
                                        color=rx.cond(TrackerState.selected_receive.contains(name), "#101010", "#dceaf7"),
                                        border=f"1px solid {LINE}",
                                        border_radius="10px",
                                        transition="all 160ms ease",
                                        width="100%",
                                        justify_content="start",
                                    ),
                                ),
                                width="100%",
                                spacing="2",
                                align="start",
                            ),
                            max_height="260px",
                            overflow_y="auto",
                            width="100%",
                        ),
                        width="100%",
                        spacing="2",
                        align="start",
                    ),
                    background="rgba(15,15,35,0.35)",
                    border=f"1px solid {LINE}",
                    border_radius="12px",
                    padding="0.7rem",
                    width="100%",
                ),
                columns="repeat(auto-fit, minmax(320px, 1fr))",
                width="100%",
                spacing="3",
            ),
        ),
        section_card(
            "Trade Message",
            "Finalize the draft and commit once the trade is confirmed.",
            rx.text_area(
                value=TrackerState.trade_message,
                read_only=True,
                min_height="170px",
                background=SURFACE,
                border=f"1px solid {LINE}",
                font_family="'Fira Code', monospace",
            ),
            rx.hstack(
                rx.button("Copy message", on_click=rx.set_clipboard(TrackerState.trade_message), background=SURFACE, border=f"1px solid {LINE}", color=TEXT),
                rx.button("Trade done", on_click=TrackerState.apply_trade_commit, background=f"linear-gradient(120deg, {ACCENT} 0%, {ACCENT_DEEP} 100%)", color="#021018"),
                wrap="wrap",
                spacing="3",
            ),
            rx.box(
                rx.text(TrackerState.trade_status, color=MUTED, font_size="0.87rem"),
                width="100%",
                background="rgba(15,15,35,0.35)",
                border=f"1px solid {LINE}",
                border_radius="10px",
                padding="0.55rem 0.7rem",
            ),
        ),
        width="100%",
        spacing="4",
        background=SURFACE,
        border=f"1px solid {LINE}",
        border_radius="16px",
        padding="1.1rem",
        box_shadow="0 10px 26px rgba(0,0,0,0.28)",
    )


def metamob_tab() -> rx.Component:
    return rx.vstack(
        rx.hstack(
            rx.text("Metamob Profile Updater", font_weight="700", font_size="1.15rem", color=TEXT),
            rx.spacer(),
            width="100%",
        ),
        section_card(
            "Profile Controls",
            "Prepare and sync your profile update payload.",
            rx.hstack(
                rx.text("Selected character:", color=MUTED, font_size="0.85rem"),
                rx.text(TrackerState.current_character_name, color=TEXT, font_weight="700", font_size="0.9rem"),
                width="100%",
                align="center",
            ),
            rx.hstack(
                rx.vstack(
                    rx.text("Metamob API key", color=MUTED, font_size="0.85rem"),
                    rx.input(
                        placeholder="Paste your Metamob API key",
                        value=TrackerState.mm_api_key,
                        on_change=TrackerState.set_mm_api_key,
                        type="password",
                        width="420px",
                        background=SURFACE,
                        border=f"1px solid {LINE}",
                    ),
                    align="start",
                    spacing="1",
                ),
                rx.button(
                    "Save API key",
                    on_click=TrackerState.save_mm_api_key,
                    background=SURFACE,
                    border=f"1px solid {LINE}",
                    color=TEXT,
                ),
                width="100%",
                wrap="wrap",
                align="end",
                spacing="3",
            ),
            rx.hstack(
                rx.button(
                    "Generate JSON from tracker",
                    on_click=TrackerState.generate_mm_body,
                    background=f"linear-gradient(120deg, {ACCENT} 0%, {ACCENT_DEEP} 100%)",
                    color="#021018",
                ),
                rx.button("Copy JSON", on_click=rx.set_clipboard(TrackerState.mm_body), background=SURFACE, border=f"1px solid {LINE}", color=TEXT),
                rx.button("Send update", on_click=TrackerState.send_metamob_update, background=SURFACE, border=f"1px solid {LINE}", color=TEXT),
                rx.button("Force validated trades", on_click=TrackerState.force_validated_trades, background=SURFACE, border=f"1px solid {LINE}", color=TEXT),
                rx.button("Reset monsters", on_click=TrackerState.reset_metamob_monsters, background=SURFACE, border=f"1px solid {LINE}", color=TEXT),
                wrap="wrap",
                spacing="3",
                width="100%",
            ),
            rx.text(TrackerState.metamob_estimate, color=MUTED, font_size="0.87rem"),
            rx.text_area(
                value=TrackerState.mm_body,
                on_change=TrackerState.set_mm_body,
                min_height="240px",
                background=SURFACE,
                border=f"1px solid {LINE}",
                font_family="'Fira Code', monospace",
            ),
        ),
        section_card(
            "Quest Settings",
            "Load, edit, and persist Metamob quest options.",
            rx.hstack(
                rx.button("Load quest settings", on_click=TrackerState.load_quest_settings, background=SURFACE, border=f"1px solid {LINE}", color=TEXT),
                rx.button("Save quest settings", on_click=TrackerState.save_quest_settings, background=SURFACE, border=f"1px solid {LINE}", color=TEXT),
                wrap="wrap",
                spacing="3",
            ),
            rx.cond(
                TrackerState.mm_settings_loaded,
                rx.vstack(
                    rx.hstack(
                        rx.input(
                            placeholder="Character name",
                            value=TrackerState.mm_qs_character_name,
                            on_change=TrackerState.set_mm_qs_character_name,
                            background=SURFACE,
                            border=f"1px solid {LINE}",
                            width="100%",
                        ),
                        rx.input(
                            placeholder="Parallel quests",
                            value=TrackerState.mm_qs_parallel_quests,
                            on_change=TrackerState.set_mm_qs_parallel_quests,
                            type="number",
                            background=SURFACE,
                            border=f"1px solid {LINE}",
                            width="100%",
                        ),
                        width="100%",
                        spacing="3",
                        wrap="wrap",
                    ),
                    rx.hstack(
                        rx.input(
                            value=TrackerState.mm_qs_current_step,
                            is_read_only=True,
                            background=SURFACE,
                            border=f"1px solid {LINE}",
                            width="100%",
                        ),
                        rx.select(
                            ["0", "1"],
                            value=TrackerState.mm_qs_trade_mode,
                            on_change=TrackerState.set_mm_qs_trade_mode,
                            background=SURFACE,
                            border=f"1px solid {LINE}",
                            width="100%",
                        ),
                        width="100%",
                        spacing="3",
                        wrap="wrap",
                    ),
                    rx.cond(
                        TrackerState.mm_qs_trade_mode == "1",
                        rx.hstack(
                            rx.input(
                                placeholder="Offer threshold",
                                value=TrackerState.mm_qs_offer_threshold,
                                on_change=TrackerState.set_mm_qs_offer_threshold,
                                type="number",
                                background=SURFACE,
                                border=f"1px solid {LINE}",
                                width="100%",
                            ),
                            rx.input(
                                placeholder="Want threshold",
                                value=TrackerState.mm_qs_want_threshold,
                                on_change=TrackerState.set_mm_qs_want_threshold,
                                type="number",
                                background=SURFACE,
                                border=f"1px solid {LINE}",
                                width="100%",
                            ),
                            width="100%",
                            spacing="3",
                            wrap="wrap",
                        ),
                    ),
                    rx.box(
                        rx.vstack(
                            rx.hstack(
                                rx.checkbox(
                                    checked=TrackerState.mm_qs_show_trades,
                                    on_change=TrackerState.set_mm_qs_show_trades,
                                ),
                                rx.text("Visible in community"),
                            ),
                            rx.hstack(
                                rx.checkbox(
                                    checked=TrackerState.mm_qs_never_offer_normal,
                                    on_change=TrackerState.set_mm_qs_never_offer_normal,
                                ),
                                rx.text("Never offer normal"),
                            ),
                            rx.hstack(
                                rx.checkbox(
                                    checked=TrackerState.mm_qs_never_want_normal,
                                    on_change=TrackerState.set_mm_qs_never_want_normal,
                                ),
                                rx.text("Never want normal"),
                            ),
                            rx.hstack(
                                rx.checkbox(
                                    checked=TrackerState.mm_qs_never_offer_boss,
                                    on_change=TrackerState.set_mm_qs_never_offer_boss,
                                ),
                                rx.text("Never offer boss"),
                            ),
                            rx.hstack(
                                rx.checkbox(
                                    checked=TrackerState.mm_qs_never_want_boss,
                                    on_change=TrackerState.set_mm_qs_never_want_boss,
                                ),
                                rx.text("Never want boss"),
                            ),
                            rx.hstack(
                                rx.checkbox(
                                    checked=TrackerState.mm_qs_never_offer_arch,
                                    on_change=TrackerState.set_mm_qs_never_offer_arch,
                                ),
                                rx.text("Never offer arch"),
                            ),
                            rx.hstack(
                                rx.checkbox(
                                    checked=TrackerState.mm_qs_never_want_arch,
                                    on_change=TrackerState.set_mm_qs_never_want_arch,
                                ),
                                rx.text("Never want arch"),
                            ),
                            width="100%",
                            align="start",
                            spacing="2",
                        ),
                        width="100%",
                        background=SURFACE,
                        border=f"1px solid {LINE}",
                        border_radius="12px",
                        padding="0.8rem",
                    ),
                    width="100%",
                    align="start",
                    spacing="3",
                ),
            ),
        ),
        rx.text(TrackerState.mm_status, color=MUTED, font_size="0.87rem"),
        width="100%",
        spacing="4",
        background=SURFACE,
        border=f"1px solid {LINE}",
        border_radius="16px",
        padding="1.1rem",
        box_shadow="0 10px 26px rgba(0,0,0,0.28)",
    )
