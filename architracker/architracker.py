import reflex as rx

from architracker.pages.index import index
from architracker.state import TrackerState


app = rx.App(
    theme=rx.theme(
        appearance="dark",
        has_background=True,
        radius="large",
        accent_color="teal",
    )
)
app.add_page(index, on_load=TrackerState.initialize, title="ArchiTracker")

