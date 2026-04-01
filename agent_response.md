```json
[
  {
    "path": "src/flet_app.py",
    "content": "import flet as ft\n\ndef main(page: ft.Page):\n    page.title = \"Hello World\"\n    page.add(\n        ft.Text(\"Hello, world!\"),\n        ft.ElevatedButton(\"Click me\", on_click=lambda e: print(\"Clicked!\"))\n    )\n\nif __name__ == \"__main__\":\n    ft.app(target=main)\n"
  }
]
```