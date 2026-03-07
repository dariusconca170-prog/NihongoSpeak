import flet as ft
from config import Colors
import time

class Sidebar(ft.Container):
    def __init__(self, on_change):
        super().__init__()
        self.on_change = on_change
        self.width = 240
        self.bgcolor = Colors.BG_SIDEBAR
        self.padding = ft.padding.all(24)
        
        # Safe border assignment
        try:
            self.border = ft.border.only(right=ft.BorderSide(1, Colors.BORDER_DEFAULT))
        except:
            pass
        
        self.controls_list = ft.Column(
            spacing=8,
            expand=True,
        )
        
        self.content = ft.Column(
            controls=[
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Text("日本語", size=22, weight="bold", color=Colors.ACCENT_RED),
                            ft.Text("Sensei", size=22, weight="bold", color=Colors.TEXT_PRIMARY),
                        ],
                        spacing=0,
                    ),
                    margin=ft.margin.only(bottom=32),
                ),
                self.controls_list,
            ],
            expand=True,
        )
        
        # Add items
        self.controls_list.controls.extend([
            self._nav_item("💬  Chat", "chat", True),
            self._nav_item("📖  Review", "review"),
            self._nav_item("📊  Vocab", "vocab"),
            ft.Container(expand=True),
            self._nav_item("⚙️  Settings", "settings"),
        ])

    def _nav_item(self, text, id, selected=False):
        c = ft.Container(
            content=ft.Text(
                text, 
                size=14, 
                weight="w500", 
                color=Colors.TEXT_PRIMARY if selected else Colors.TEXT_SECONDARY
            ),
            padding=ft.padding.symmetric(10, 16),
            border_radius=10,
            bgcolor=Colors.BORDER_DEFAULT if selected else None,
            data=id,
            animate=ft.Animation(200, "easeOut"),
        )
        c.on_click = lambda _: self.on_change(id)
        c.on_hover = self._on_hover
        
        try:
            c.mouse_cursor = "pointer"
        except:
            pass
        return c

    def set_selected(self, id):
        self.selected_id = id
        for item in self.controls_list.controls:
            if isinstance(item, ft.Container) and item.data:
                is_selected = item.data == id
                item.bgcolor = Colors.BORDER_DEFAULT if is_selected else None
                if hasattr(item.content, "color"):
                    item.content.color = Colors.TEXT_PRIMARY if is_selected else Colors.TEXT_SECONDARY
        self.update()

    def _on_hover(self, e):
        if e.control.data != getattr(self, "selected_id", "chat"):
            e.control.bgcolor = "white05" if e.data == "true" else None
            e.control.update()

class ChatBubble(ft.Container):
    def __init__(self, role, text):
        super().__init__()
        is_assistant = role == "assistant"
        self.content = ft.Text(
            text, 
            color=Colors.TEXT_PRIMARY, 
            size=15, 
            weight="w400",
            selectable=True,
        )
        self.bgcolor = Colors.AI_BUBBLE if is_assistant else Colors.USER_BUBBLE
        self.padding = ft.padding.all(16)
        self.border_radius = 15
        
        # Entrance Animation tokens
        self.opacity = 0
        self.offset = ft.Offset(0, 0.1)
        self.animate_opacity = ft.Animation(400, "easeOut")
        self.animate_offset = ft.Animation(400, "easeOut")

    def did_mount(self):
        self.opacity = 1
        self.offset = ft.Offset(0, 0)
        self.update()

class ModernCard(ft.Container):
    def __init__(self, content, title=None):
        super().__init__()
        self.bgcolor = "white05"
        self.border_radius = 12
        self.padding = ft.padding.all(20)
        
        # Safe border
        try:
            self.border = ft.border.all(1, Colors.BORDER_DEFAULT)
        except:
            pass
        
        controls = []
        if title:
            controls.append(ft.Text(title, size=16, weight="bold", color=Colors.TEXT_PRIMARY))
            controls.append(ft.Divider(height=16, color=Colors.BORDER_DEFAULT))
        
        controls.append(content)
        self.content = ft.Column(controls=controls)

class ActionButton(ft.Container):
    def __init__(self, text, on_click, primary=True):
        super().__init__()
        self.content = ft.Text(text, size=14, weight="bold", color=Colors.TEXT_INVERSE)
        self.bgcolor = Colors.ACCENT_PRIMARY if primary else "white10"
        self.padding = ft.padding.symmetric(10, 20)
        self.border_radius = 10
        self._internal_on_click = on_click

        self.on_click = self._on_click
        self.on_hover = self._on_hover
        self.animate = ft.Animation(200, "easeOut")
        
        try:
            self.animate_scale = ft.Animation(400, "elasticOut")
            self.scale = 1.0
            self.mouse_cursor = "pointer"
        except:
            pass
        
    def _on_hover(self, e):
        try:
            self.scale = 1.02 if e.data == "true" else 1.0
        except:
            pass
            
        if not self.bgcolor == Colors.ACCENT_PRIMARY:
            self.bgcolor = "white24" if e.data == "true" else "white10"
        self.update()

    def _on_click(self, e):
        try:
            self.scale = 0.95
            self.update()
            time.sleep(0.05)
            self.scale = 1.0
            self.update()
        except:
            pass
            
        if self._internal_on_click:
            self._internal_on_click(e)
