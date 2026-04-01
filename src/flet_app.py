import flet as ft
from flet import Colors

def main(page: ft.Page):
    page.title = "Flet App"
    bottom_border = ft.BorderSide(1, Colors.BORDER_DEFAULT)
    my_border = ft.Border(bottom=bottom_border)
    container = ft.Container(
        width=300,
        height=200,
        border=my_border,
        padding=10,
        content=ft.Text("Hello, world!"),
        alignment=ft.alignment.center,
    )
    page.add(container)
    page.update()

if __name__ == "__main__":
    ft.app(target=main)
