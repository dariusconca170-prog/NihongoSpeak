import flet as ft
from flet import Colors

def main(page: ft.Page):
    page.title = "My Flet App"
    page.window_width = 400
    page.window_height = 300

    def button_click(e):
        my_text.value = "Button clicked!"
        page.update()

    my_text = ft.Text("Hello, Flet!", size=20)
    my_button = ft.ElevatedButton("Click Me", on_click=button_click)

    container = ft.Container(
        content=ft.Column([
            my_text,
            my_button
        ]),
        padding=20,
        border=ft.border.only(
            bottom=ft.BorderSide(1, Colors.BORDER_DEFAULT)
        )
    )

    page.add(container)

ft.app(target=main)
