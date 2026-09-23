from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from PIL import Image, ImageTk

try:
    import pystray

    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False

from database import Database, InUseError
from services import (
    MONTH_NAMES,
    MONTHS,
    build_alerts,
    currency,
    export_transactions_csv,
    parse_nonnegative_amount,
    parse_positive_amount,
    validate_iso_date,
)

ctk.set_appearance_mode("system")
ctk.set_default_color_theme("blue")

NAVY = "#172554"
BLUE = "#2563EB"
CYAN = "#06B6D4"
GREEN = "#16A34A"
RED = "#DC2626"
TEXT_MUTED = "#64748B"
LIGHT_BG = "#F8FAFC"
DARK_BG = "#0F172A"
CHART_BG_LIGHT = "#FFFFFF"
CHART_FG = {"light": "#1E293B", "dark": "#E2E8F0"}

THEME_LABELS = {"System": "system", "Claro": "light", "Oscuro": "dark"}
THEME_OPTIONS = {mode: label for label, mode in THEME_LABELS.items()}

ICON_PATH = Path(__file__).resolve().parent / "assets" / "icon.ico"


def load_icon_image() -> Image.Image | None:
    try:
        return Image.open(ICON_PATH).convert("RGBA")
    except (OSError, ValueError, FileNotFoundError):
        return None


def set_window_icon(root) -> None:
    image = load_icon_image()
    if image is None:
        return
    try:
        photo = ImageTk.PhotoImage(image.resize((64, 64), Image.Resampling.LANCZOS))
        root._icon_photo = photo
        root.iconphoto(True, photo)
    except Exception:
        pass


class MetricCard(ctk.CTkFrame):
    def __init__(self, master, title: str, accent: str = BLUE):
        super().__init__(master, corner_radius=12, border_width=1, border_color=accent)
        self.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self, text=title, text_color=accent, font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=14, pady=(10, 2), sticky="w")
        self.value = ctk.CTkLabel(self, text="C$ 0.00", font=ctk.CTkFont(size=22, weight="bold"))
        self.value.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="w")

    def set(self, value: str, color: str | None = None):
        self.value.configure(text=value, text_color=color or ("#111827", "#F8FAFC"))


class FinanceApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.db = Database()
        self.selected_transaction_id: int | None = None
        self.tray = None
        self._apply_saved_theme()
        self.title("Control Financiero Pro - Córdobas Nicaragüenses")
        self.geometry("1360x820")
        self.minsize(1120, 700)
        set_window_icon(self)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_tree_style()
        self._build_layout()
        self.load_settings()
        self.refresh_all()
        self._setup_tray()

    def is_dark(self) -> bool:
        return ctk.get_appearance_mode() == "Dark"

    def _apply_saved_theme(self):
        theme = self.db.get_settings().get("theme", "system")
        if theme not in THEME_LABELS.values():
            theme = "system"
        ctk.set_appearance_mode(theme)

    def _setup_tray(self):
        if not PYSTRAY_AVAILABLE:
            return
        image = load_icon_image()
        if image is None:
            return
        try:
            from pystray import Icon as TrayIcon, Menu as TrayMenu, MenuItem as TrayMenuItem

            menu = TrayMenu(
                TrayMenuItem("Mostrar", lambda icon, item: self._show_from_tray(), default=True),
                TrayMenuItem("Ocultar", lambda icon, item: self._hide_to_tray()),
                TrayMenu.SEPARATOR,
                TrayMenuItem("Salir", lambda icon, item: self._quit_app()),
            )
            self.tray = TrayIcon("control_financiero_pro", image, "Control Financiero", menu)
            self.tray.run_detached()
        except Exception:
            self.tray = None

    def _show_from_tray(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _hide_to_tray(self):
        self.withdraw()

    def _on_close(self):
        if self.tray is not None:
            self._hide_to_tray()
        else:
            self.destroy()

    def _quit_app(self):
        self.destroy()

    def destroy(self):
        if self.tray is not None:
            try:
                self.tray.stop()
            except Exception:
                pass
            self.tray = None
        super().destroy()

    def _configure_tree_style(self):
        dark = self.is_dark()
        bg = DARK_BG if dark else LIGHT_BG
        fg = "#E2E8F0" if dark else "#1E293B"
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", rowheight=30, font=("Arial", 10), background=bg, fieldbackground=bg, foreground=fg)
        style.configure("Treeview.Heading", font=("Arial", 10, "bold"), background=NAVY, foreground="white", relief="flat")
        style.map("Treeview", background=[("selected", BLUE)], foreground=[("selected", "white")])

    def _build_layout(self):
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.sidebar = ctk.CTkFrame(self, width=215, corner_radius=0, fg_color=NAVY)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        ctk.CTkLabel(self.sidebar, text="CONTROL\nFINANCIERO", text_color="white", font=ctk.CTkFont(size=21, weight="bold"), justify="left").pack(padx=22, pady=(28, 35), anchor="w")
        for text, command in [("Panel", self.show_dashboard), ("Movimientos", self.show_transactions), ("Configuración", self.show_settings)]:
            ctk.CTkButton(self.sidebar, text=text, command=command, height=42, anchor="w", fg_color="transparent", hover_color="#1E3A8A", font=ctk.CTkFont(size=14, weight="bold")).pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(self.sidebar, text="Datos guardados localmente\nMoneda: Córdobas (C$)", text_color="#BFDBFE", font=ctk.CTkFont(size=10), justify="left").pack(side="bottom", padx=20, pady=(0, 18), anchor="w")
        theme_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        ctk.CTkLabel(theme_frame, text="Tema", text_color="#BFDBFE", font=ctk.CTkFont(size=10)).pack(anchor="w", padx=20)
        self.theme_menu = ctk.CTkOptionMenu(theme_frame, values=list(THEME_LABELS.keys()), command=self.change_theme, width=165)
        self.theme_menu.pack(padx=20, anchor="w", pady=(4, 0))
        theme_frame.pack(side="bottom", anchor="w", padx=0, pady=(0, 8))

        self.container = ctk.CTkFrame(self, corner_radius=0, fg_color=("#F8FAFC", "#0F172A"))
        self.container.grid(row=0, column=1, sticky="nsew")
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)
        self.frames = {}
        self._build_dashboard()
        self._build_transactions()
        self._build_settings()
        self.show_dashboard()

    def _page(self, name: str):
        frame = ctk.CTkFrame(self.container, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew", padx=22, pady=18)
        self.frames[name] = frame
        return frame

    def _header(self, parent, title: str, subtitle: str):
        ctk.CTkLabel(parent, text=title, font=ctk.CTkFont(size=26, weight="bold"), text_color=(NAVY, "#E2E8F0")).pack(anchor="w")
        sub = ctk.CTkLabel(parent, text=subtitle, text_color=TEXT_MUTED, font=ctk.CTkFont(size=12))
        sub.pack(anchor="w", pady=(0, 14))
        return sub

    def _build_dashboard(self):
        page = self._page("dashboard")
        top = ctk.CTkFrame(page, fg_color="transparent")
        top.pack(fill="x")
        title_box = ctk.CTkFrame(top, fg_color="transparent")
        title_box.pack(side="left", fill="x", expand=True)
        self.dashboard_sub = self._header(title_box, "Panel financiero", "Indicadores dinámicos en córdobas nicaragüenses")
        filters = ctk.CTkFrame(top, fg_color="transparent")
        filters.pack(side="right", anchor="ne")
        self.period_var = ctk.StringVar(value="Todo el año")
        self.year_var = ctk.StringVar(value=str(date.today().year))
        ctk.CTkLabel(filters, text="Periodo").grid(row=0, column=0, padx=5)
        ctk.CTkOptionMenu(filters, variable=self.period_var, values=list(MONTHS.keys()), command=lambda _: self.refresh_dashboard(), width=150).grid(row=1, column=0, padx=5)
        ctk.CTkLabel(filters, text="Año").grid(row=0, column=1, padx=5)
        self.year_menu = ctk.CTkOptionMenu(filters, variable=self.year_var, values=[str(y) for y in range(date.today().year - 5, date.today().year + 26)], command=lambda _: self.refresh_dashboard(), width=95)
        self.year_menu.grid(row=1, column=1, padx=5)

        cards = ctk.CTkFrame(page, fg_color="transparent")
        cards.pack(fill="x", pady=(4, 12))
        for i in range(4):
            cards.grid_columnconfigure(i, weight=1)
        self.income_card = MetricCard(cards, "INGRESOS", BLUE)
        self.income_card.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.expense_card = MetricCard(cards, "GASTOS", RED)
        self.expense_card.grid(row=0, column=1, padx=6, sticky="ew")
        self.profit_card = MetricCard(cards, "UTILIDAD", GREEN)
        self.profit_card.grid(row=0, column=2, padx=6, sticky="ew")
        self.balance_card = MetricCard(cards, "SALDO ACTUAL", CYAN)
        self.balance_card.grid(row=0, column=3, padx=(6, 0), sticky="ew")

        metrics = ctk.CTkFrame(page, fg_color="transparent")
        metrics.pack(fill="x", pady=(0, 12))
        for i in range(4):
            metrics.grid_columnconfigure(i, weight=1)
        self.goal_card = MetricCard(metrics, "META DE INGRESOS", BLUE)
        self.goal_card.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.compliance_card = MetricCard(metrics, "CUMPLIMIENTO", GREEN)
        self.compliance_card.grid(row=0, column=1, padx=6, sticky="ew")
        self.limit_card = MetricCard(metrics, "USO DEL LÍMITE", RED)
        self.limit_card.grid(row=0, column=2, padx=6, sticky="ew")
        self.count_card = MetricCard(metrics, "MOVIMIENTOS", CYAN)
        self.count_card.grid(row=0, column=3, padx=(6, 0), sticky="ew")

        lower = ctk.CTkFrame(page, fg_color="transparent")
        lower.pack(fill="both", expand=True)
        lower.grid_columnconfigure(0, weight=3)
        lower.grid_columnconfigure(1, weight=2)
        lower.grid_rowconfigure(0, weight=1)
        chart_frame = ctk.CTkFrame(lower, corner_radius=12)
        chart_frame.grid(row=0, column=0, padx=(0, 8), sticky="nsew")
        self.figure = Figure(figsize=(7, 4), dpi=90)
        self.axis = self.figure.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.figure, master=chart_frame)
        self.canvas.get_tk_widget().pack(fill="both", expand=True, padx=8, pady=8)
        side = ctk.CTkFrame(lower, corner_radius=12)
        side.grid(row=0, column=1, padx=(8, 0), sticky="nsew")
        ctk.CTkLabel(side, text="Resumen por categoría", font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=14, pady=(12, 6))
        self.category_box = ctk.CTkTextbox(side, font=ctk.CTkFont(family="Courier", size=11), wrap="none")
        self.category_box.pack(fill="both", expand=True, padx=12, pady=6)
        self.status_label = ctk.CTkLabel(side, text="", font=ctk.CTkFont(size=12, weight="bold"), wraplength=340, justify="left")
        self.status_label.pack(fill="x", padx=14, pady=(4, 12), anchor="w")

    def _build_transactions(self):
        page = self._page("transactions")
        self._header(page, "Movimientos", "Registra, modifica, busca y exporta ingresos y gastos")
        form = ctk.CTkFrame(page, corner_radius=12)
        form.pack(fill="x", pady=(0, 10))
        for i in range(8):
            form.grid_columnconfigure(i, weight=1)
        self.tx_date = ctk.CTkEntry(form, placeholder_text="AAAA-MM-DD")
        self.tx_date.insert(0, date.today().isoformat())
        self.tx_type = ctk.CTkOptionMenu(form, values=["Ingreso", "Gasto"], command=self._update_category_menu)
        self.tx_category = ctk.CTkOptionMenu(form, values=["Ventas"])
        self.tx_description = ctk.CTkEntry(form, placeholder_text="Descripción")
        self.tx_method = ctk.CTkOptionMenu(form, values=["Efectivo"])
        self.tx_amount = ctk.CTkEntry(form, placeholder_text="Monto C$")
        self.tx_party = ctk.CTkEntry(form, placeholder_text="Cliente / Proveedor")
        self.tx_notes = ctk.CTkEntry(form, placeholder_text="Notas")
        widgets = [
            ("Fecha", self.tx_date),
            ("Tipo", self.tx_type),
            ("Categoría", self.tx_category),
            ("Descripción", self.tx_description),
            ("Método", self.tx_method),
            ("Monto", self.tx_amount),
            ("Cliente / Proveedor", self.tx_party),
            ("Notas", self.tx_notes),
        ]
        for i, (label, widget) in enumerate(widgets):
            ctk.CTkLabel(form, text=label, font=ctk.CTkFont(size=10, weight="bold")).grid(row=0, column=i, padx=5, pady=(8, 2), sticky="w")
            widget.grid(row=1, column=i, padx=5, pady=(0, 8), sticky="ew")

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.pack(fill="x", pady=(0, 8))
        ctk.CTkButton(actions, text="Guardar", command=self.save_transaction, fg_color=GREEN).pack(side="left", padx=(0, 6))
        ctk.CTkButton(actions, text="Limpiar", command=self.clear_transaction_form, fg_color=TEXT_MUTED).pack(side="left", padx=6)
        ctk.CTkButton(actions, text="Eliminar", command=self.delete_selected_transaction, fg_color=RED).pack(side="left", padx=6)
        ctk.CTkButton(actions, text="Duplicar", command=self.duplicate_selected_transaction, fg_color=NAVY).pack(side="left", padx=6)
        ctk.CTkButton(actions, text="Exportar CSV", command=self.export_csv).pack(side="right")
        self.search_var = ctk.StringVar()
        search = ctk.CTkEntry(actions, textvariable=self.search_var, placeholder_text="Buscar movimiento...", width=260)
        search.pack(side="right", padx=8)
        search.bind("<KeyRelease>", lambda _: self.refresh_transactions())

        filters = ctk.CTkFrame(page, fg_color="transparent")
        filters.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(filters, text="Desde", font=ctk.CTkFont(size=10, weight="bold")).pack(side="left")
        self.tx_from = ctk.CTkEntry(filters, width=110, placeholder_text="AAAA-MM-DD")
        self.tx_from.pack(side="left", padx=(4, 12))
        self.tx_from.bind("<KeyRelease>", lambda _: self.refresh_transactions())
        ctk.CTkLabel(filters, text="Hasta", font=ctk.CTkFont(size=10, weight="bold")).pack(side="left")
        self.tx_to = ctk.CTkEntry(filters, width=110, placeholder_text="AAAA-MM-DD")
        self.tx_to.pack(side="left", padx=(4, 12))
        self.tx_to.bind("<KeyRelease>", lambda _: self.refresh_transactions())
        ctk.CTkLabel(filters, text="Tipo", font=ctk.CTkFont(size=10, weight="bold")).pack(side="left")
        self.tx_filter_type = ctk.CTkOptionMenu(filters, values=["Todos", "Ingreso", "Gasto"], command=lambda _: self.refresh_transactions(), width=120)
        self.tx_filter_type.pack(side="left", padx=(4, 0))

        columns = ("id", "date", "type", "category", "description", "method", "amount", "party")
        self.tree = ttk.Treeview(page, columns=columns, show="headings", selectmode="browse")
        labels = ("ID", "Fecha", "Tipo", "Categoría", "Descripción", "Método", "Monto C$", "Cliente / Proveedor")
        widths = (55, 100, 90, 150, 230, 120, 115, 160)
        for col, label, width in zip(columns, labels, widths):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="w")
        self.tree.column("amount", anchor="e")
        scroll = ttk.Scrollbar(page, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.load_selected_transaction)

    def _build_settings(self):
        page = self._page("settings")
        self._header(page, "Configuración", "Personaliza el negocio, metas, categorías y métodos de pago")
        top = ctk.CTkFrame(page, corner_radius=12)
        top.pack(fill="x", pady=(0, 12))
        for i in range(5):
            top.grid_columnconfigure(i, weight=1)
        self.business_entry = ctk.CTkEntry(top)
        self.initial_entry = ctk.CTkEntry(top)
        self.goal_entry = ctk.CTkEntry(top)
        self.limit_entry = ctk.CTkEntry(top)
        self.settings_year = ctk.CTkEntry(top)
        fields = [
            ("Nombre del negocio", self.business_entry),
            ("Saldo inicial C$", self.initial_entry),
            ("Meta de ingresos C$", self.goal_entry),
            ("Límite de gastos C$", self.limit_entry),
            ("Año", self.settings_year),
        ]
        for i, (label, widget) in enumerate(fields):
            ctk.CTkLabel(top, text=label, font=ctk.CTkFont(size=10, weight="bold")).grid(row=0, column=i, padx=8, pady=(10, 3), sticky="w")
            widget.grid(row=1, column=i, padx=8, pady=(0, 10), sticky="ew")
        ctk.CTkButton(page, text="Guardar configuración", command=self.save_settings, fg_color=GREEN).pack(anchor="w", pady=(0, 12))
        lists = ctk.CTkFrame(page, fg_color="transparent")
        lists.pack(fill="both", expand=True)
        for i in range(3):
            lists.grid_columnconfigure(i, weight=1)
            lists.grid_rowconfigure(0, weight=1)
        self.income_list = self._list_editor(lists, "Categorías de ingresos", "Ingreso", 0)
        self.expense_list = self._list_editor(lists, "Categorías de gastos", "Gasto", 1)
        self.payment_list = self._list_editor(lists, "Métodos de pago", "Pago", 2)

    def _list_editor(self, parent, title, kind, column):
        frame = ctk.CTkFrame(parent, corner_radius=12)
        frame.grid(row=0, column=column, padx=6, sticky="nsew")
        ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=12, pady=(12, 6))
        box = ctk.CTkTextbox(frame, height=260)
        box.pack(fill="both", expand=True, padx=12, pady=6)
        box.configure(state="disabled")
        entry = ctk.CTkEntry(frame, placeholder_text="Nueva opción")
        entry.pack(fill="x", padx=12, pady=5)
        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=(2, 12))
        ctk.CTkButton(buttons, text="Agregar", width=90, command=lambda: self.add_list_item(kind, entry)).pack(side="left")
        ctk.CTkButton(buttons, text="Eliminar", width=90, fg_color=RED, command=lambda: self.delete_list_item(kind, entry)).pack(side="right")
        return box

    def show_dashboard(self):
        self.frames["dashboard"].tkraise()
        self.refresh_dashboard()

    def show_transactions(self):
        self.frames["transactions"].tkraise()
        self.refresh_transactions()

    def show_settings(self):
        self.frames["settings"].tkraise()
        self.load_settings()
        self.refresh_lists()

    def refresh_all(self):
        methods = self.db.payment_methods()
        if not methods:
            self.db.add_payment_method("Efectivo")
            methods = ["Efectivo"]
        self._update_category_menu(self.tx_type.get())
        self.tx_method.configure(values=methods)
        self.tx_method.set(methods[0])
        self.refresh_dashboard()
        self.refresh_transactions()
        self.refresh_lists()
        self._update_business_title()

    def _update_business_title(self, name: str | None = None):
        if name is None:
            name = self.db.get_settings().get("business_name", "Mi Negocio") or "Mi Negocio"
        self.title(f"{name} — Control Financiero Pro")
        if hasattr(self, "dashboard_sub"):
            self.dashboard_sub.configure(text=f"Indicadores dinámicos de {name} · Córdobas nicaragüenses")

    def change_theme(self, label: str):
        mode = THEME_LABELS.get(label, "system")
        ctk.set_appearance_mode(mode)
        self.db.update_settings({"theme": mode})
        self._configure_tree_style()
        self.refresh_dashboard()
        self.refresh_transactions()

    def refresh_dashboard(self):
        try:
            year = int(self.year_var.get())
        except ValueError:
            return
        month = MONTHS.get(self.period_var.get())
        settings = self.db.get_settings()
        summary = self.db.summary(year, month)
        initial = float(settings.get("initial_balance", 0) or 0)
        alerts = build_alerts(settings, summary)
        self.income_card.set(currency(summary["income"]))
        self.expense_card.set(currency(summary["expense"]))
        self.profit_card.set(currency(summary["profit"]), GREEN if summary["profit"] >= 0 else RED)
        self.balance_card.set(currency(initial + summary["profit"]))
        self.goal_card.set(currency(alerts["goal"]))
        self.compliance_card.set(f"{alerts['compliance']:.1f}%", GREEN if alerts["compliance"] >= 100 else None)
        self.limit_card.set(f"{alerts['used']:.1f}%", RED if alerts["used"] > 100 else None)
        self.count_card.set(str(summary["count"]))
        self.category_box.configure(state="normal")
        self.category_box.delete("1.0", "end")
        if summary["categories"]:
            for row in summary["categories"][:12]:
                self.category_box.insert("end", f"{row['category'][:20]:20} {row['type'][:1]}  {currency(row['total']):>16}\n")
        else:
            self.category_box.insert("end", "No hay movimientos en este periodo.")
        self.category_box.configure(state="disabled")
        bad = summary["profit"] < 0 or alerts["used"] > 100
        self.status_label.configure(text="\n".join(alerts["messages"]), text_color=RED if bad else GREEN)
        self._draw_chart(year)

    def _draw_chart(self, year: int):
        dark = self.is_dark()
        bg = DARK_BG if dark else CHART_BG_LIGHT
        fg = CHART_FG["dark" if dark else "light"]
        monthly = self.db.monthly_summary(year)
        self.axis.clear()
        x = list(range(1, 13))
        incomes = [r["income"] for r in monthly]
        expenses = [r["expense"] for r in monthly]
        self.figure.set_facecolor(bg)
        self.axis.set_facecolor(bg)
        self.axis.plot(x, incomes, color=BLUE, marker="o", linewidth=2, label="Ingresos")
        self.axis.plot(x, expenses, color=RED, marker="o", linewidth=2, label="Gastos")
        self.axis.set_title(f"Ingresos vs. gastos mensuales - {year}", color=fg)
        self.axis.set_xticks(x, MONTH_NAMES, rotation=35, ha="right", fontsize=8)
        self.axis.tick_params(axis="both", labelsize=8, colors=fg)
        self.axis.grid(axis="y", alpha=0.25)
        legend = self.axis.legend(frameon=False, loc="upper left")
        for text in legend.get_texts():
            text.set_color(fg)
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def _transaction_payload(self):
        description = self.tx_description.get().strip()
        if not description:
            raise ValueError("Escribe una descripción.")
        return {
            "date": validate_iso_date(self.tx_date.get()),
            "type": self.tx_type.get(),
            "category": self.tx_category.get(),
            "description": description,
            "payment_method": self.tx_method.get(),
            "amount": parse_positive_amount(self.tx_amount.get()),
            "party": self.tx_party.get().strip(),
            "notes": self.tx_notes.get().strip(),
        }

    def save_transaction(self):
        try:
            payload = self._transaction_payload()
            if self.selected_transaction_id:
                self.db.update_transaction(self.selected_transaction_id, payload)
                message = "Movimiento actualizado."
            else:
                self.db.add_transaction(payload)
                message = "Movimiento guardado."
            self.clear_transaction_form()
            self.refresh_transactions()
            self.refresh_dashboard()
            messagebox.showinfo("Éxito", message)
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror("No se pudo guardar", str(exc))

    def clear_transaction_form(self):
        self.selected_transaction_id = None
        for entry in [self.tx_date, self.tx_description, self.tx_amount, self.tx_party, self.tx_notes]:
            entry.delete(0, "end")
        self.tx_date.insert(0, date.today().isoformat())
        self.tx_type.set("Ingreso")
        self._update_category_menu("Ingreso")

    def load_selected_transaction(self, _=None):
        selected = self.tree.selection()
        if not selected:
            return
        values = self.tree.item(selected[0], "values")
        self.selected_transaction_id = int(values[0])
        rows = [r for r in self.db.transactions() if r["id"] == self.selected_transaction_id]
        if not rows:
            return
        row = rows[0]
        for entry, value in [
            (self.tx_date, row["date"]),
            (self.tx_description, row["description"]),
            (self.tx_amount, str(row["amount"])),
            (self.tx_party, row["party"]),
            (self.tx_notes, row["notes"]),
        ]:
            entry.delete(0, "end")
            entry.insert(0, value)
        self.tx_type.set(row["type"])
        self._update_category_menu(row["type"])
        self.tx_category.set(row["category"])
        self.tx_method.set(row["payment_method"])

    def duplicate_selected_transaction(self):
        if not self.selected_transaction_id:
            messagebox.showwarning("Selecciona un movimiento", "Elige una fila antes de duplicar.")
            return
        self.load_selected_transaction()
        self.selected_transaction_id = None

    def delete_selected_transaction(self):
        if not self.selected_transaction_id:
            messagebox.showwarning("Selecciona un movimiento", "Elige una fila antes de eliminar.")
            return
        if messagebox.askyesno("Confirmar", "¿Eliminar el movimiento seleccionado?"):
            self.db.delete_transaction(self.selected_transaction_id)
            self.clear_transaction_form()
            self.refresh_transactions()
            self.refresh_dashboard()

    def _filter_dates(self):
        start = self.tx_from.get().strip() if hasattr(self, "tx_from") else ""
        end = self.tx_to.get().strip() if hasattr(self, "tx_to") else ""
        try:
            start = validate_iso_date(start) if start else None
        except ValueError:
            start = None
        try:
            end = validate_iso_date(end) if end else None
        except ValueError:
            end = None
        return start, end

    def _transaction_filters(self):
        filters = {"search": self.search_var.get().strip() if hasattr(self, "search_var") else ""}
        start, end = self._filter_dates()
        if start:
            filters["start"] = start
        if end:
            filters["end"] = end
        tx_type = getattr(self, "tx_filter_type", None)
        if tx_type is not None:
            value = tx_type.get()
            if value != "Todos":
                filters["transaction_type"] = value
        return filters

    def refresh_transactions(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in self.db.transactions(**self._transaction_filters()):
            self.tree.insert("", "end", values=(row["id"], row["date"], row["type"], row["category"], row["description"], row["payment_method"], currency(row["amount"]), row["party"]))

    def export_csv(self):
        path = filedialog.asksaveasfilename(title="Exportar movimientos", defaultextension=".csv", filetypes=[("Archivo CSV", "*.csv")])
        if not path:
            return
        rows = self.db.transactions(**self._transaction_filters())
        export_transactions_csv(rows, path)
        messagebox.showinfo("Exportación completa", f"Archivo guardado en:\n{path}")

    def _update_category_menu(self, transaction_type):
        values = self.db.categories(transaction_type)
        current = self.tx_category.get()
        if values:
            self.tx_category.configure(values=values)
            self.tx_category.set(current if current in values else values[0])
        else:
            self.tx_category.configure(values=["Sin categoría"])
            self.tx_category.set("Sin categoría")

    def load_settings(self):
        settings = self.db.get_settings()
        for entry, key in [
            (self.business_entry, "business_name"),
            (self.initial_entry, "initial_balance"),
            (self.goal_entry, "income_goal"),
            (self.limit_entry, "expense_limit"),
            (self.settings_year, "analysis_year"),
        ]:
            entry.delete(0, "end")
            entry.insert(0, settings.get(key, ""))
        if hasattr(self, "year_var"):
            self.year_var.set(settings.get("analysis_year", str(date.today().year)))
        if hasattr(self, "theme_menu"):
            self.theme_menu.set(THEME_OPTIONS.get(settings.get("theme", "system"), "System"))
        self._update_business_title(settings.get("business_name", "Mi Negocio") or "Mi Negocio")

    def save_settings(self):
        try:
            year = int(self.settings_year.get())
            initial = parse_nonnegative_amount(self.initial_entry.get())
            goal = parse_positive_amount(self.goal_entry.get())
            limit = parse_positive_amount(self.limit_entry.get())
            if not 2000 <= year <= 2100:
                raise ValueError("El año debe estar entre 2000 y 2100.")
            theme = self.db.get_settings().get("theme", "system")
            self.db.update_settings({
                "business_name": self.business_entry.get().strip() or "Mi Negocio",
                "initial_balance": str(initial),
                "income_goal": str(goal),
                "expense_limit": str(limit),
                "analysis_year": str(year),
                "theme": theme,
            })
            self.year_var.set(str(year))
            self._update_business_title(self.business_entry.get().strip() or "Mi Negocio")
            self.refresh_dashboard()
            messagebox.showinfo("Éxito", "Configuración guardada.")
        except ValueError as exc:
            messagebox.showerror("Datos inválidos", str(exc))

    def refresh_lists(self):
        for box, values in [
            (self.income_list, self.db.categories("Ingreso")),
            (self.expense_list, self.db.categories("Gasto")),
            (self.payment_list, self.db.payment_methods()),
        ]:
            box.configure(state="normal")
            box.delete("1.0", "end")
            box.insert("end", "\n".join(values))
            box.configure(state="disabled")

    def add_list_item(self, kind, entry):
        value = entry.get().strip()
        if not value:
            return
        try:
            if kind == "Pago":
                self.db.add_payment_method(value)
            else:
                self.db.add_category(value, kind)
            entry.delete(0, "end")
            self.refresh_lists()
            self.refresh_all()
        except (ValueError, sqlite3.IntegrityError) as exc:
            messagebox.showwarning("Opción no válida", str(exc))

    def delete_list_item(self, kind, entry):
        value = entry.get().strip()
        if not value:
            messagebox.showwarning("Escribe una opción", "Escribe exactamente la opción que deseas eliminar.")
            return
        remaining = self.db.payment_methods() if kind == "Pago" else self.db.categories(kind)
        if value in remaining and len(remaining) <= 1:
            messagebox.showwarning("Opción necesaria", "Debe conservar al menos una opción en esta lista.")
            return
        try:
            if kind == "Pago":
                self.db.delete_payment_method(value)
            else:
                self.db.delete_category(value, kind)
            entry.delete(0, "end")
            self.refresh_lists()
            self.refresh_all()
        except InUseError as exc:
            messagebox.showwarning("No se puede eliminar", str(exc))


if __name__ == "__main__":
    try:
        FinanceApp().mainloop()
    except Exception as exc:
        messagebox.showerror("Error de inicio", f"La aplicación no pudo iniciarse:\n{exc}")