"""LeadDock — local-first prospecting CRM. Python 3.10+ / PySide6."""
import html, queue, re, sqlite3, sys, threading
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QUrl, QDate
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QPlainTextEdit, QComboBox, QTableWidget, QTableWidgetItem, QSplitter, QFormLayout,
    QFileDialog, QMessageBox, QTabWidget, QHeaderView, QSystemTrayIcon, QMenu, QStyle, QFrame, QAbstractItemView,
    QDialog, QScrollArea, QTextBrowser, QCalendarWidget, QDialogButtonBox, QSizePolicy, QListWidget, QListWidgetItem,
    QStyledItemDelegate, QButtonGroup, QInputDialog)

import bridge, enrich, store
from store import STAGES, PRIORITIES, ACTIVITY_TYPES

STAGE_COLORS = {'New': '#8b9bff', 'Qualified': '#45c8e6', 'Contacted': '#f5bd4f', 'Follow Up': '#ff9b45',
                'Proposal': '#b993ff', 'Won': '#4fd68f', 'Lost': '#8a94a6'}
PRIORITY_COLORS = {'Low': '#8a94a6', 'Normal': '#c9d3e6', 'High': '#ffb15c', 'Urgent': '#ff6b6b'}
ACTION_COLORS = {'Note': '#c9d3e6', 'Call': '#6fd3a6', 'Email': '#7fb2ff', 'Text': '#7fb2ff', 'Visit': '#f5bd4f',
                 'Meeting': '#b993ff', 'Stage': '#ff9b45', 'Priority': '#ff9b45', 'Follow-up': '#ff9b45',
                 'Captured': '#8b9bff', 'Refreshed': '#8b9bff', 'Website scan': '#45c8e6'}
WARN, HOT, MUTED, GOOD = '#ff6b6b', '#ffb15c', '#7d8aa3', '#4fd68f'
USER_ACTIONS = set(ACTIVITY_TYPES)  # timeline entries you typed yourself can be edited and deleted
# Quick call outcomes shown on each lead (the call session shows all of store.CALL_OUTCOMES).
QUICK_OUTCOMES = ['No answer', 'Left voicemail', 'Interested', 'Call back later', 'Not interested']
COLUMNS = ['Business', 'Type', 'Stage', 'Phone', 'Follow-up', 'Last note', 'Website', 'City', 'Rating', 'Priority', 'Last contact']
COLUMN_WIDTHS = {'Business': 220, 'Type': 178, 'Stage': 84, 'Phone': 112, 'Follow-up': 92, 'Last note': 210, 'Website': 140,
                 'City': 115, 'Rating': 92, 'Priority': 66, 'Last contact': 84}
HIDDEN_BY_DEFAULT = ['Priority', 'Last contact']

STYLE = '''
QWidget { background:#0d111b; color:#e9edf7; font-family:'Segoe UI'; font-size:12px; }
QMainWindow, QDialog { background:#0d111b; }
QLabel#heading { font-size:21px; font-weight:700; } QLabel#brand { font-size:20px; font-weight:700; }
QLabel#phone { font-size:28px; font-weight:700; color:#ffffff; }
QLabel#hint { color:#93a0b8; } QLabel#section { color:#8ea0c2; font-size:11px; font-weight:700; letter-spacing:1px; }
QLabel#filters { color:#c9d3e6; }
QFrame#panel { background:#151b2a; border:1px solid #293248; border-radius:12px; }
QLineEdit, QPlainTextEdit, QComboBox, QTextBrowser { background:#121929; border:1px solid #303a50; border-radius:7px; padding:6px; selection-background-color:#4364db; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border:1px solid #6e8df9; }
QLineEdit:read-only { color:#93a0b8; }
QComboBox QAbstractItemView { background:#151b2a; border:1px solid #303a50; selection-background-color:#34446b; }
QPushButton { background:#252e43; border:1px solid #35415a; border-radius:7px; padding:7px 11px; font-weight:600; }
QPushButton:hover { background:#34425e; } QPushButton:disabled { color:#5d6880; }
QPushButton#primary { background:#566ff0; border:0; color:white; } QPushButton#primary:hover { background:#7189ff; }
QPushButton#primary:disabled { background:#2e3a63; color:#8c97b8; }
QPushButton#call { background:#1f6f4a; border:0; color:white; } QPushButton#call:hover { background:#278a5c; }
QPushButton#danger { background:#3a1f27; border:1px solid #5a2a36; color:#ffb3bd; }
QPushButton#outcome { padding:6px 9px; font-weight:600; }
QPushButton#outcome:checked { background:#4057b1; border:1px solid #6e8df9; color:white; }
QPushButton#link { background:transparent; border:0; color:#8fa8ff; padding:2px 4px; }
QPushButton#link:hover { color:#b5c6ff; }
QTableWidget { background:#121929; alternate-background-color:#161f33; gridline-color:#1f293d; border:1px solid #283247; border-radius:8px; }
QHeaderView::section { background:#1c2538; color:#b5c1d6; border:0; padding:8px; font-weight:600; }
QTableWidget::item { padding:4px; } QTableWidget::item:selected { background:#34446b; color:white; }
QTabWidget::pane { border:0; } QTabBar::tab { padding:8px 14px; background:#182032; margin-right:5px; border-radius:7px; }
QTabBar::tab:selected { background:#4057b1; } QSplitter::handle { background:#1c2538; }
QListWidget#facet { background:transparent; border:0; outline:0; }
QListWidget#facet::item { padding:5px 38px 5px 8px; border-radius:6px; margin:1px 0; }
QListWidget#facet::item:hover { background:#1a2337; }
QListWidget#facet::item:selected { background:#2b3a62; color:white; }
QMenu { background:#151b2a; border:1px solid #303a50; padding:4px; } QMenu::item { padding:6px 22px; border-radius:5px; }
QMenu::item:selected { background:#34446b; } QMenu::separator { height:1px; background:#2a344a; margin:4px 8px; }
QToolTip { background:#1c2538; color:#e9edf7; border:1px solid #35415a; padding:5px; }
QScrollBar:vertical { background:#101624; width:10px; } QScrollBar::handle:vertical { background:#39445d; border-radius:5px; min-height:24px; }
QScrollBar:horizontal { background:#101624; height:10px; } QScrollBar::handle:horizontal { background:#39445d; border-radius:5px; }
QScrollBar::add-line, QScrollBar::sub-line { width:0; height:0; }
QCalendarWidget QWidget { alternate-background-color:#151b2a; } QCalendarWidget QToolButton { color:#e9edf7; background:#252e43; border-radius:5px; padding:4px; }
'''


def chip(text, color):
    return f'<span style="color:{color}; font-weight:600">●&nbsp;{html.escape(text)}</span>'


def nice_time(stamp):
    try:
        dt = datetime.strptime(stamp[:19], '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError):
        return stamp or ''
    day = 'Today' if dt.date() == date.today() else dt.strftime('%b %d, %Y' if dt.year != date.today().year else '%b %d')
    return f"{day} {dt.strftime('%I:%M %p').lstrip('0')}"


def nice_date(iso):
    d = store.valid_date(iso)
    if not d:
        return ''
    d = date.fromisoformat(d)
    return d.strftime('%b %d' if d.year == date.today().year else '%b %d, %Y')


def plural(n, word):
    return f'{n} {word}{"" if n == 1 else "s"}'


def lead_flags(row):
    flags = []
    if not row['website']:
        flags.append(('No website', HOT))
    elif row['website_issues']:
        flags.append(('Website issues', HOT))
    if row['claimed'] == 'No':
        flags.append(('Unclaimed profile', HOT))
    if (row['business_status'] or '').lower().endswith('closed'):
        flags.append((row['business_status'], WARN))
    if row['next_followup'] and row['next_followup'] <= date.today().isoformat() and row['status'] not in store.CLOSED_STAGES:
        flags.append(('Follow-up due', WARN))
    return flags


def dial(phone):
    """Hand the number to Windows' calling app (Phone Link, Teams, Skype…)."""
    digits = re.sub(r'[^\d+]', '', phone or '')
    if digits:
        QDesktopServices.openUrl(QUrl('tel:' + digits))


def section(text):
    label = QLabel(text)
    label.setObjectName('section')
    return label


class Signals(QObject):
    bridge_event = Signal(str, int, str)
    scan_done = Signal(int, str)


class WebsiteScanner:
    """Scans lead websites one at a time on a background thread."""

    def __init__(self, signals):
        self.signals, self.jobs, self.pending = signals, queue.Queue(), set()
        threading.Thread(target=self.work, daemon=True, name='leaddock-scanner').start()

    def add(self, lead_id):
        if lead_id not in self.pending:
            self.pending.add(lead_id)
            self.jobs.put(lead_id)

    def work(self):
        while True:
            lead_id = self.jobs.get()
            try:
                row = store.get_lead(lead_id)
                if not row:
                    message = ''
                elif not row['website']:
                    message = f"{row['name']} has no website to scan — a good website prospect."
                else:
                    updates = store.apply_website_scan(lead_id, enrich.scan_website(row['website']))
                    issues = updates.get('website_issues')
                    message = f"Scanned {store.site_domain(row['website'])}: " + (issues or 'no major issues') + \
                              (f" · found {updates['email']}" if updates.get('email') else '')
            except Exception as e:
                message = f'Website scan failed: {e}'
            finally:
                self.pending.discard(lead_id)
            self.signals.scan_done.emit(lead_id, message)


class SortItem(QTableWidgetItem):
    """Table cell that sorts by a hidden key (numbers, dates) instead of its display text."""

    def __init__(self, text, key=None):
        super().__init__(text)
        self.key = text.lower() if key is None else key

    def __lt__(self, other):
        try:
            return self.key < other.key
        except TypeError:
            return str(self.key) < str(other.key)


class DatePickDialog(QDialog):
    def __init__(self, parent, current):
        super().__init__(parent)
        self.setWindowTitle('Pick follow-up date')
        lay = QVBoxLayout(self)
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(False)
        if current:
            self.calendar.setSelectedDate(QDate.fromString(current, 'yyyy-MM-dd'))
        self.calendar.activated.connect(self.accept)
        lay.addWidget(self.calendar)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def value(self):
        return self.calendar.selectedDate().toString('yyyy-MM-dd')


def followup_menu(parent, current, apply):
    """Quick follow-up choices shared by the details panel, the call session and the table's right-click menu."""
    menu = QMenu(parent)
    for label, days in [('Today', 0), ('Tomorrow', 1), ('In 2 days', 2), ('In 3 days', 3), ('Next week', 7), ('In 2 weeks', 14), ('In a month', 30)]:
        menu.addAction(f"{label}  ({nice_date(store.quick_date(days))})", lambda checked=False, d=days: apply(store.quick_date(d)))

    def pick():
        dialog = DatePickDialog(parent, current)
        if dialog.exec():
            apply(dialog.value())
    menu.addAction('Pick a date…', pick)
    menu.addSeparator()
    menu.addAction('No follow-up', lambda: apply(''))
    return menu


def followup_text(due):
    label = store.followup_label(due or '')
    if not label:
        return 'Set follow-up ▾'
    if label.startswith(('Overdue', 'Today', 'Tomorrow')):
        return f'{label} · {nice_date(due)} ▾'
    return f'{label} ▾'


class StageBar(QWidget):
    """One-click pipeline stage buttons, colored like the stage."""
    picked = Signal(str)

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons = {}
        for stage in STAGES:
            b = QPushButton(stage)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            color = STAGE_COLORS[stage]
            b.setStyleSheet(f'QPushButton {{ padding:6px 4px; color:{color}; font-weight:600; }}'
                            f'QPushButton:checked {{ background:{color}; color:#0d111b; border:1px solid {color}; }}')
            b.clicked.connect(lambda checked=False, s=stage: self.picked.emit(s))
            self.group.addButton(b)
            self.buttons[stage] = b
            lay.addWidget(b)

    def set_stage(self, stage):
        button = self.buttons.get(stage) or self.buttons['New']
        button.setChecked(True)


class CountDelegate(QStyledItemDelegate):
    """Draws each filter option's count on the right."""

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        count = index.data(Qt.ItemDataRole.UserRole + 1)
        if count is not None:
            painter.save()
            painter.setPen(QColor('#7d8aa3'))
            painter.drawText(option.rect.adjusted(0, 0, -10, 0), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f'{count:,}')
            painter.restore()


class FilterList(QListWidget):
    """A sidebar filter (business type, stage, city…): pick one option, see how many leads each would show."""
    changed = Signal()

    def __init__(self, all_label):
        super().__init__()
        self.setObjectName('facet')
        self.all_label = all_label
        self.updating = False
        self.setItemDelegate(CountDelegate(self))
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.itemSelectionChanged.connect(lambda: None if self.updating else self.changed.emit())

    def key(self):
        items = self.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else ''

    def set_key(self, key):
        for i in range(self.count()):
            if self.item(i).data(Qt.ItemDataRole.UserRole) == key:
                self.setCurrentRow(i)
                return

    def set_options(self, options, total):
        """options: [(key, label, count, color)]; the 'All' option is added first."""
        current = self.key()
        if current and current not in [o[0] for o in options]:
            options = options + [(current, current, 0, None)]  # keep a chosen option visible even when it has 0 leads
        self.updating = True
        self.clear()
        for key, label, count, color in [('', self.all_label, total, None)] + options:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setData(Qt.ItemDataRole.UserRole + 1, count)
            item.setToolTip(f'{label}: {count:,}')
            if color:
                item.setForeground(QColor(color))
            self.addItem(item)
            if key == current:
                self.setCurrentItem(item)
        if not self.selectedItems():
            self.setCurrentRow(0)
        self.updating = False
        self.setFixedHeight(max(1, self.count()) * max(26, self.sizeHintForRow(0)) + 6)


class LeadDetails(QWidget):
    """Right-hand panel: one-click stage, type/priority/follow-up, quick call logging, notes timeline, business info."""

    def __init__(self, window):
        super().__init__()
        self.window, self.lead_id, self.row, self.loading, self.pending = window, None, None, False, {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 4, 4, 8)
        lay.setSpacing(7)

        self.title = QLabel('Select a lead')
        self.title.setObjectName('heading')
        self.title.setWordWrap(True)
        self.subtitle = QLabel('Pick a business on the left, or capture one from Google Maps with the browser extension.')
        self.subtitle.setObjectName('hint')
        self.subtitle.setWordWrap(True)
        self.flags = QLabel('')
        self.flags.setTextFormat(Qt.TextFormat.RichText)
        for w in (self.title, self.subtitle, self.flags):
            lay.addWidget(w)

        lay.addWidget(section('STAGE'))
        self.stage = StageBar()
        self.stage.picked.connect(lambda s: self.set_pipeline({'status': s}))
        lay.addWidget(self.stage)

        quick = QGridLayout()
        quick.setHorizontalSpacing(8)
        quick.setVerticalSpacing(3)
        lay.addLayout(quick)
        self.industry = QComboBox()
        self.industry.setEditable(True)
        self.industry.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.industry.setToolTip('Business type — used for filtering. Pick one or type your own.')
        self.industry.activated.connect(lambda *_: self.set_industry())
        self.industry.lineEdit().editingFinished.connect(self.set_industry)
        self.priority = QComboBox()
        self.priority.addItems(PRIORITIES)
        self.priority.currentTextChanged.connect(lambda v: self.set_pipeline({'priority': v}))
        self.followup = QPushButton('Set follow-up ▾')
        self.followup.clicked.connect(self.followup_clicked)
        for col, (label, widget, stretch) in enumerate([('BUSINESS TYPE', self.industry, 3), ('PRIORITY', self.priority, 2), ('FOLLOW-UP', self.followup, 3)]):
            quick.addWidget(section(label), 0, col)
            quick.addWidget(widget, 1, col)
            quick.setColumnStretch(col, stretch)

        links = QHBoxLayout()
        links.setSpacing(5)
        lay.addLayout(links)
        self.buttons = {}
        for key, text, handler in [('call', '📞 Call', lambda: dial(self.row['phone'])),
                                   ('phone', 'Copy phone', lambda: self.copy('phone')),
                                   ('maps', '↗ Maps', lambda: self.open_url(self.row['maps_url'] or store.maps_search_url(self.row['name'], self.row['address']))),
                                   ('web', '↗ Website', lambda: self.open_url(self.row['website'])),
                                   ('email', 'Copy email', lambda: self.copy('email')),
                                   ('scan', 'Scan site', self.scan)]:
            b = QPushButton(text)
            b.clicked.connect(handler)
            links.addWidget(b)
            self.buttons[key] = b
        self.buttons['call'].setObjectName('call')
        self.buttons['call'].setToolTip('Opens your calling app (Phone Link, Teams, Skype…)')

        self.tabs = QTabWidget()
        lay.addWidget(self.tabs, 1)
        self.tabs.addTab(self.build_activity_tab(), 'Notes && activity')
        self.tabs.addTab(self.build_info_tab(), 'Business info')
        self.tabs.addTab(self.build_website_tab(), 'Website && social')

        footer = QHBoxLayout()
        lay.addLayout(footer)
        self.saved = QLabel('')
        self.saved.setObjectName('hint')
        footer.addWidget(self.saved, 1)
        self.delete = QPushButton('Delete lead')
        self.delete.setObjectName('danger')
        self.delete.clicked.connect(lambda: self.window.delete_ids([self.lead_id]))
        footer.addWidget(self.delete)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.save_pending)
        self.set_lead(None)

    # ---------------------------------------------------------------- tabs
    def build_activity_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(2, 8, 2, 2)
        lay.setSpacing(5)
        lay.addWidget(section('LOG A CALL — ONE CLICK'))
        outcomes = QHBoxLayout()
        outcomes.setSpacing(4)
        lay.addLayout(outcomes)
        for outcome in QUICK_OUTCOMES:
            b = QPushButton(outcome)
            b.setObjectName('outcome')
            kind, stage, days = store.CALL_OUTCOMES[outcome]
            b.setToolTip(f'Logs a {kind.lower()}' + (f', moves the stage to {stage}' if stage else '') +
                         (', clears the follow-up' if days == '' else f', follow-up in {plural(days, "day")}' if days else '') +
                         '. Anything typed in the note box below is added to it.')
            b.clicked.connect(lambda checked=False, o=outcome: self.log_outcome(o))
            outcomes.addWidget(b)

        lay.addWidget(section('ADD A NOTE'))
        row = QHBoxLayout()
        lay.addLayout(row)
        self.composer = QPlainTextEdit()
        self.composer.setPlaceholderText('What happened? e.g. "Spoke with Pastor Tim — wants a quote for a new site by Friday."  (Ctrl+Enter to add)')
        self.composer.setMaximumHeight(70)
        side = QVBoxLayout()
        self.note_type = QComboBox()
        self.note_type.addItems(ACTIVITY_TYPES)
        self.add_button = QPushButton('Add')
        self.add_button.setObjectName('primary')
        self.add_button.clicked.connect(self.add_activity)
        side.addWidget(self.note_type)
        side.addWidget(self.add_button)
        row.addWidget(self.composer, 1)
        row.addLayout(side)
        for keys in ('Ctrl+Return', 'Ctrl+Enter'):
            QShortcut(QKeySequence(keys), self.composer, self.add_activity, context=Qt.ShortcutContext.WidgetShortcut)

        lay.addWidget(section('PINNED NOTES'))
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText('Always-visible summary: decision maker, what they need, objections, pricing discussed…')
        self.notes.setMaximumHeight(64)
        self.notes.textChanged.connect(lambda: self.queue_save('notes', self.notes.toPlainText()))
        lay.addWidget(self.notes)

        lay.addWidget(section('TIMELINE'))
        self.timeline = QTextBrowser()
        self.timeline.setOpenLinks(False)
        self.timeline.anchorClicked.connect(self.timeline_link)
        lay.addWidget(self.timeline, 1)
        return w

    def build_info_tab(self):
        form_widget = QWidget()
        form = QFormLayout(form_widget)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(7)
        self.fields = {}
        multiline = ('hours',)
        readonly = ('place_id', 'source')
        for f in ['name', 'category', 'contact_name', 'phone', 'email', 'website', 'address', 'city', 'state', 'postal_code',
                  'estimated_value', 'rating', 'review_count', 'hours', 'business_status', 'claimed', 'price_level',
                  'plus_code', 'maps_url', 'place_id', 'source']:
            if f == 'claimed':
                c = QComboBox()
                c.addItems(['Unknown', 'Claimed', 'Unclaimed'])
                c.currentTextChanged.connect(lambda v: self.queue_save('claimed', {'Unknown': '', 'Claimed': 'Yes', 'Unclaimed': 'No'}[v], 50))
            elif f in multiline:
                c = QPlainTextEdit()
                c.setMaximumHeight(110)
                c.textChanged.connect(lambda f=f, c=c: self.queue_save(f, c.toPlainText()))
            else:
                c = QLineEdit()
                c.setReadOnly(f in readonly)
                c.textEdited.connect(lambda v, f=f: self.queue_save(f, v))
            label = 'Deal value ($)' if f == 'estimated_value' else store.LABELS[f]
            form.addRow(label + ':', c)
            self.fields[f] = c
        self.stamps = QLabel('')
        self.stamps.setObjectName('hint')
        form.addRow('', self.stamps)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(form_widget)
        return scroll

    def build_website_tab(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(2, 8, 2, 2)
        self.issues = QLabel('')
        self.issues.setWordWrap(True)
        self.issues.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.issues)
        row = QHBoxLayout()
        self.scanned = QLabel('')
        self.scanned.setObjectName('hint')
        row.addWidget(self.scanned, 1)
        scan = QPushButton('Scan website now')
        scan.clicked.connect(self.scan)
        row.addWidget(scan)
        lay.addLayout(row)
        lay.addWidget(section('WEBSITE AUDIT'))
        self.audit = QPlainTextEdit()
        self.audit.setReadOnly(True)
        self.audit.setPlaceholderText('Scan the website to check HTTPS, mobile-friendliness, platform, copyright year and find emails/social links.')
        lay.addWidget(self.audit, 1)
        lay.addWidget(section('SOCIAL LINKS (one per line)'))
        self.socials = QPlainTextEdit()
        self.socials.setMaximumHeight(90)
        self.socials.textChanged.connect(lambda: self.queue_save('social_links', self.socials.toPlainText()))
        lay.addWidget(self.socials)
        open_all = QPushButton('Open social links')
        open_all.clicked.connect(lambda: [self.open_url(l) for l in self.socials.toPlainText().split() if l.startswith('http')])
        lay.addWidget(open_all)
        return w

    # ---------------------------------------------------------------- loading
    def set_lead(self, row):
        self.save_pending()
        self.loading = True
        self.row = row
        self.lead_id = row['id'] if row else None
        enabled = bool(row)
        for w in [self.stage, self.industry, self.priority, self.followup, self.tabs, self.delete, *self.buttons.values()]:
            w.setEnabled(enabled)
        if not row:
            self.title.setText('Select a lead')
            self.subtitle.setText('Pick a business on the left, or capture one from Google Maps with the browser extension.')
            self.flags.setText('')
            self.saved.setText('')
            for c in [self.notes, self.composer, self.audit, self.socials, *[f for f in self.fields.values() if not isinstance(f, QComboBox)]]:
                c.clear() if isinstance(c, QPlainTextEdit) else c.setText('')
            self.timeline.clear()
            self.followup.setText('Set follow-up ▾')
            self.industry.setEditText('')
            self.loading = False
            return
        self.title.setText(row['name'])
        self.refresh_header()
        self.stage.set_stage(row['status'])
        self.priority.setCurrentText(row['priority'] if row['priority'] in PRIORITIES else 'Normal')
        self.load_industries(row['industry'] or 'Other')
        self.update_followup_button()
        self.notes.setPlainText(row['notes'] or '')
        for f, c in self.fields.items():
            value = row[f]
            if f == 'estimated_value':
                value = f'{value:g}' if isinstance(value, (int, float)) and value else ''
            if isinstance(c, QComboBox):
                c.setCurrentText({'Yes': 'Claimed', 'No': 'Unclaimed'}.get(row['claimed'], 'Unknown'))
            elif isinstance(c, QPlainTextEdit):
                c.setPlainText(str(value or ''))
            else:
                c.setText(str(value or ''))
                c.setCursorPosition(0)
        self.stamps.setText(f"Created {nice_time(row['created_at'])} · Updated {nice_time(row['updated_at'])}")
        self.update_buttons()
        self.load_website(row)
        self.load_timeline()
        self.saved.setText('Changes save automatically')
        self.loading = False

    def load_industries(self, current):
        self.industry.blockSignals(True)
        self.industry.clear()
        self.industry.addItems(store.industries_in_use())
        self.industry.setCurrentText(current)
        self.industry.blockSignals(False)

    def update_buttons(self):
        self.buttons['web'].setEnabled(bool(self.row['website']))
        self.buttons['phone'].setEnabled(bool(self.row['phone']))
        self.buttons['call'].setEnabled(bool(self.row['phone']))
        self.buttons['email'].setEnabled(bool(self.row['email']))

    def refresh_header(self):
        row = self.row
        bits = [row['category'], ', '.join(x for x in (row['city'], row['state']) if x)]
        if row['rating']:
            bits.append(f"★ {row['rating']}" + (f" ({int(row['review_count']):,} reviews)" if (row['review_count'] or '').isdigit() else ''))
        bits.append(row['phone'])
        self.subtitle.setText('  ·  '.join(b for b in bits if b) or 'No details yet — fill in Business info')
        flags = lead_flags(row)
        self.flags.setText('&nbsp;&nbsp;&nbsp;'.join(chip(t, c) for t, c in flags))
        self.flags.setVisible(bool(flags))

    def load_website(self, row):
        if not row['website']:
            self.issues.setText(chip('No website on the Google profile — prime prospect for a new site.', HOT))
        elif row['website_issues']:
            self.issues.setText(' &nbsp; '.join(chip(i.strip(), HOT) for i in row['website_issues'].split(',')))
        elif row['website_scanned_at']:
            self.issues.setText(chip('No major website issues found', GOOD))
        else:
            self.issues.setText(chip('Not scanned yet', MUTED))
        self.scanned.setText(f"Last scanned {nice_time(row['website_scanned_at'])}" if row['website_scanned_at'] else '')
        self.audit.setPlainText(row['website_audit'] or '')
        if self.socials.toPlainText() != (row['social_links'] or ''):
            self.socials.setPlainText(row['social_links'] or '')

    def load_timeline(self):
        parts = []
        for a in store.list_activities(self.lead_id):
            color = ACTION_COLORS.get(a['action'], '#c9d3e6')
            tools = (f' &nbsp;<a href="edit:{a["id"]}" style="color:#7d8aa3; text-decoration:none">edit</a>'
                     f' &nbsp;<a href="delete:{a["id"]}" style="color:#7d8aa3; text-decoration:none">✕</a>') if a['action'] in USER_ACTIONS else ''
            detail = html.escape(a['detail'] or '').replace('\n', '<br>')
            parts.append(f'<div style="margin-bottom:9px"><span style="color:{color}; font-weight:700">{html.escape(a["action"])}</span>'
                         f'<span style="color:#7d8aa3"> &nbsp;·&nbsp; {nice_time(a["at"])}</span>{tools}<br>{detail}</div>')
        self.timeline.setHtml(''.join(parts) or '<span style="color:#7d8aa3">No activity yet.</span>')

    def reload(self):
        if self.lead_id:
            row = store.get_lead(self.lead_id)
            focus = QApplication.focusWidget()
            if row and focus in (self.notes, self.socials, self.composer, self.industry.lineEdit(), *self.fields.values()):
                # Don't yank text out from under the user; just refresh the read-only parts.
                self.row = row
                self.refresh_header()
                self.load_timeline()
                self.update_followup_button()
                self.loading = True
                self.stage.set_stage(row['status'])
                self.loading = False
            else:
                self.set_lead(row)

    # ---------------------------------------------------------------- saving
    def queue_save(self, field, value, delay=600):
        if self.loading or not self.lead_id:
            return
        self.pending[field] = value
        self.saved.setText('Editing…')
        self.timer.start(delay)

    def save_pending(self):
        if not self.lead_id or not self.pending:
            return
        changes, self.pending = self.pending, {}
        try:
            store.update_lead(self.lead_id, changes, log=False)
        except ValueError as e:
            self.saved.setText('⚠ ' + str(e))
            return
        self.saved.setText('✓ Saved')
        self.row = store.get_lead(self.lead_id)
        if 'name' in changes:
            self.title.setText(self.row['name'])
        if self.industry.currentText() != self.row['industry']:  # renaming a hand-typed lead can fill in its type
            self.load_industries(self.row['industry'])
        self.refresh_header()
        self.update_buttons()
        self.window.lead_changed(self.lead_id)

    def set_pipeline(self, changes):
        if self.loading or not self.lead_id:
            return
        try:
            store.update_lead(self.lead_id, changes)
        except ValueError as e:
            self.saved.setText('⚠ ' + str(e))
            return
        self.row = store.get_lead(self.lead_id)
        self.refresh_header()
        self.update_followup_button()
        self.load_timeline()
        self.saved.setText('✓ Saved')
        self.window.lead_changed(self.lead_id)

    def set_industry(self):
        value = self.industry.currentText().strip()
        if not self.loading and self.lead_id and value and value != (self.row['industry'] or ''):
            self.set_pipeline({'industry': value})
            self.saved.setText(f'✓ Filed under {value}')

    def update_followup_button(self):
        due = (self.row['next_followup'] if self.row else '') or ''
        self.followup.setText(followup_text(due))
        self.followup.setStyleSheet(f'color:{WARN};' if due and due <= date.today().isoformat() else '')

    def followup_clicked(self):
        menu = followup_menu(self, self.row['next_followup'], lambda d: self.set_pipeline({'next_followup': d}))
        menu.exec(self.followup.mapToGlobal(self.followup.rect().bottomLeft()))

    def after_log(self, message):
        self.composer.clear()
        self.note_type.setCurrentText('Note')
        self.row = store.get_lead(self.lead_id)
        self.loading = True
        self.stage.set_stage(self.row['status'])
        self.loading = False
        self.refresh_header()
        self.update_followup_button()
        self.load_timeline()
        self.saved.setText(message)
        self.window.lead_changed(self.lead_id)

    def add_activity(self):
        if not self.lead_id:
            return
        text, kind = self.composer.toPlainText().strip(), self.note_type.currentText()
        try:
            extra = store.add_activity(self.lead_id, kind, text)
        except ValueError as e:
            self.saved.setText('⚠ ' + str(e))
            return
        self.after_log(f'✓ {kind} logged' + (f" · stage moved to {extra['status']}" if extra.get('status') else ''))

    def log_outcome(self, outcome):
        if not self.lead_id:
            return
        kind, stage, followup = store.outcome_plan(outcome, self.row['status'])
        note = self.composer.toPlainText().strip()
        extra = store.add_activity(self.lead_id, kind, outcome + (f' — {note}' if note else ''), status=stage, next_followup=followup)
        bits = [f'✓ Logged: {outcome}']
        if extra.get('status'):
            bits.append(f"stage → {extra['status']}")
        if 'next_followup' in extra:
            bits.append(f"follow-up {nice_date(extra['next_followup'])}" if extra['next_followup'] else 'follow-up cleared')
        self.after_log(' · '.join(bits))

    def start_log(self, kind):
        self.tabs.setCurrentIndex(0)
        self.note_type.setCurrentText(kind)
        self.composer.setFocus()

    def timeline_link(self, url):
        action, _, activity_id = url.toString().partition(':')
        if not activity_id.isdigit():
            return
        if action == 'delete' and QMessageBox.question(self, 'Delete entry', 'Delete this timeline entry?') == QMessageBox.StandardButton.Yes:
            store.delete_activity(int(activity_id))
        elif action == 'edit':
            current = next((a['detail'] for a in store.list_activities(self.lead_id) if a['id'] == int(activity_id)), '')
            text, ok = QInputDialog.getMultiLineText(self, 'Edit entry', 'Note:', current)
            if not ok:
                return
            store.update_activity(int(activity_id), text)
        self.load_timeline()
        self.window.lead_changed(self.lead_id)

    # ---------------------------------------------------------------- actions
    def open_url(self, url):
        if url:
            QDesktopServices.openUrl(QUrl(store.clean_url(url)))

    def copy(self, field):
        if self.row and self.row[field]:
            QApplication.clipboard().setText(self.row[field])
            self.saved.setText(f'Copied {self.row[field]}')

    def scan(self):
        if self.lead_id:
            self.save_pending()
            self.window.scan_ids([self.lead_id])


class CallSession(QDialog):
    """Work through a list of leads one at a time: call, pick what happened, add a note, next."""

    def __init__(self, window, ids, title):
        super().__init__(window)
        self.window, self.ids, self.index, self.results = window, list(ids), 0, {}
        self.outcome, self.followup_value, self.loading = None, None, False
        self.setWindowTitle('Call session — ' + title)
        self.setStyleSheet(STYLE)
        self.resize(780, 760)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(8)

        top = QHBoxLayout()
        lay.addLayout(top)
        heading = QLabel(f'📞  Calling {title}')
        heading.setTextFormat(Qt.TextFormat.PlainText)
        heading.setObjectName('brand')
        top.addWidget(heading)
        top.addStretch()
        self.progress = QLabel('')
        self.progress.setObjectName('hint')
        top.addWidget(self.progress)

        self.name = QLabel('')
        self.name.setObjectName('heading')
        self.name.setWordWrap(True)
        self.sub = QLabel('')
        self.sub.setObjectName('hint')
        self.sub.setWordWrap(True)
        self.flags = QLabel('')
        self.flags.setTextFormat(Qt.TextFormat.RichText)
        for w in (self.name, self.sub, self.flags):
            lay.addWidget(w)

        phone_row = QHBoxLayout()
        lay.addLayout(phone_row)
        self.phone = QLabel('')
        self.phone.setObjectName('phone')
        self.phone.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        phone_row.addWidget(self.phone)
        phone_row.addSpacing(10)
        self.call = QPushButton('📞 Call')
        self.call.setObjectName('call')
        self.call.setToolTip('Opens your calling app (Phone Link, Teams, Skype…)')
        self.call.clicked.connect(lambda: dial(self.row['phone']))
        copy = QPushButton('Copy number')
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.row['phone'] or ''))
        self.site = QPushButton('↗ Website')
        self.site.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(store.clean_url(self.row['website']))))
        maps = QPushButton('↗ Maps')
        maps.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.row['maps_url'] or store.maps_search_url(self.row['name'], self.row['address']))))
        for b in (self.call, copy, self.site, maps):
            phone_row.addWidget(b)
        phone_row.addStretch()

        lay.addWidget(section('PINNED NOTES'))
        self.notes = QPlainTextEdit()
        self.notes.setMaximumHeight(58)
        self.notes.setPlaceholderText('Decision maker, what they need… (saved automatically)')
        self.notes_timer = QTimer(self)
        self.notes_timer.setSingleShot(True)
        self.notes_timer.timeout.connect(self.save_notes)
        self.notes.textChanged.connect(lambda: None if self.loading else self.notes_timer.start(600))
        lay.addWidget(self.notes)
        lay.addWidget(section('RECENT ACTIVITY'))
        self.history = QTextBrowser()
        self.history.setMaximumHeight(120)
        lay.addWidget(self.history)

        lay.addWidget(section('WHAT HAPPENED?   (Alt+1 … Alt+7)'))
        grid = QGridLayout()
        grid.setSpacing(5)
        lay.addLayout(grid)
        self.outcome_buttons = QButtonGroup(self)
        for i, outcome in enumerate(store.CALL_OUTCOMES):
            b = QPushButton(f'{i + 1}  {outcome}')
            b.setObjectName('outcome')
            b.setCheckable(True)
            b.clicked.connect(lambda checked=False, o=outcome: self.pick_outcome(o))
            self.outcome_buttons.addButton(b, i)
            grid.addWidget(b, i // 4, i % 4)
            QShortcut(QKeySequence(f'Alt+{i + 1}'), self, lambda o=outcome, b=b: (b.setChecked(True), self.pick_outcome(o)))
        self.note = QPlainTextEdit()
        self.note.setMaximumHeight(70)
        self.note.setPlaceholderText('Notes from the call (optional) — e.g. "Pastor Tim, wants a quote, call Thursday"')
        lay.addWidget(self.note)

        plan = QHBoxLayout()
        lay.addLayout(plan)
        plan.addWidget(QLabel('Stage:'))
        self.stage = QComboBox()
        self.stage.addItems(STAGES)
        plan.addWidget(self.stage)
        plan.addSpacing(14)
        plan.addWidget(QLabel('Follow-up:'))
        self.followup = QPushButton('')
        self.followup.clicked.connect(self.followup_clicked)
        plan.addWidget(self.followup)
        plan.addStretch()

        nav = QHBoxLayout()
        lay.addLayout(nav)
        self.back = QPushButton('◀ Previous')
        self.back.clicked.connect(lambda: self.go(self.index - 1))
        skip = QPushButton('Skip ▶')
        skip.clicked.connect(lambda: self.go(self.index + 1))
        end = QPushButton('End session')
        end.clicked.connect(self.finish)
        self.status = QLabel('')
        self.status.setObjectName('hint')
        self.save_next = QPushButton('Save && next ▶   (Ctrl+Enter)')
        self.save_next.setObjectName('primary')
        self.save_next.clicked.connect(self.save_and_next)
        for w in (self.back, skip, end):
            nav.addWidget(w)
        nav.addWidget(self.status, 1)
        nav.addWidget(self.save_next)
        for keys in ('Ctrl+Return', 'Ctrl+Enter'):
            QShortcut(QKeySequence(keys), self, self.save_and_next)
        self.load()

    def load(self):
        self.row = store.get_lead(self.ids[self.index])
        if not self.row:  # deleted meanwhile
            del self.ids[self.index]
            return self.finish() if not self.ids else self.go(min(self.index, len(self.ids) - 1))
        r = self.row
        self.loading = True
        self.progress.setText(f'Lead {self.index + 1} of {len(self.ids)}  ·  {plural(len(self.results), "call")} logged')
        self.name.setText(r['name'])
        bits = [r['industry'], r['category'], ', '.join(x for x in (r['city'], r['state']) if x),
                f"★ {r['rating']}" if r['rating'] else '', f"Contact: {r['contact_name']}" if r['contact_name'] else '',
                f"Stage: {r['status']}", f"Last contacted {nice_date(r['last_contacted'])}" if r['last_contacted'] else 'Never contacted']
        self.sub.setText('  ·  '.join(b for b in bits if b))
        flags = lead_flags(r)
        self.flags.setText('&nbsp;&nbsp;&nbsp;'.join(chip(t, c) for t, c in flags))
        self.flags.setVisible(bool(flags))
        self.phone.setText(r['phone'] or 'No phone number')
        self.call.setEnabled(bool(r['phone']))
        self.site.setEnabled(bool(r['website']))
        self.notes.setPlainText(r['notes'] or '')
        items = [a for a in store.list_activities(r['id'], 8)]
        self.history.setHtml(''.join(
            f'<div><span style="color:{ACTION_COLORS.get(a["action"], "#c9d3e6")}; font-weight:700">{html.escape(a["action"])}</span>'
            f'<span style="color:#7d8aa3"> · {nice_time(a["at"])}</span> — {html.escape(a["detail"] or "")}</div>' for a in items)
            or '<span style="color:#7d8aa3">No activity yet — first call.</span>')
        self.outcome_buttons.setExclusive(False)
        for b in self.outcome_buttons.buttons():
            b.setChecked(False)
        self.outcome_buttons.setExclusive(True)
        self.outcome = None
        self.note.clear()
        self.stage.setCurrentText(r['status'] if r['status'] in STAGES else 'New')
        self.set_followup(r['next_followup'] or '')
        self.back.setEnabled(self.index > 0)
        done = self.results.get(r['id'])
        self.status.setText(f'Already logged this session: {done}' if done else '')
        self.loading = False
        self.note.setFocus()

    def set_followup(self, value):
        self.followup_value = value
        self.followup.setText(followup_text(value).replace(' ▾', '') + ' ▾' if value else 'None ▾')

    def followup_clicked(self):
        menu = followup_menu(self, self.followup_value, self.set_followup)
        menu.exec(self.followup.mapToGlobal(self.followup.rect().bottomLeft()))

    def pick_outcome(self, outcome):
        self.outcome = outcome
        _, stage, followup = store.outcome_plan(outcome, self.row['status'])
        self.stage.setCurrentText(stage or self.row['status'])
        if followup is not None:
            self.set_followup(followup)
        self.status.setText(f'{outcome}: ' + ', '.join(x for x in (
            f'stage → {stage}' if stage else '', f'follow-up {nice_date(followup)}' if followup else 'no follow-up' if followup == '' else '') if x))

    def save_notes(self):
        if self.row and self.notes.toPlainText() != (self.row['notes'] or ''):
            store.update_lead(self.row['id'], {'notes': self.notes.toPlainText()}, log=False)

    def save_current(self):
        """Log what happened for the current lead. Returns False when there was nothing to save."""
        self.notes_timer.stop()
        self.save_notes()
        r, note = self.row, self.note.toPlainText().strip()
        stage = self.stage.currentText()
        stage_change = stage if stage != r['status'] else None
        followup_change = self.followup_value if self.followup_value != (r['next_followup'] or '') else None
        if self.outcome:
            kind = store.CALL_OUTCOMES[self.outcome][0]
            store.add_activity(r['id'], kind, self.outcome + (f' — {note}' if note else ''), status=stage_change, next_followup=followup_change)
            self.results[r['id']] = self.outcome
        elif note:
            store.add_activity(r['id'], 'Note', note, status=stage_change, next_followup=followup_change)
            self.results[r['id']] = 'Note'
        elif stage_change or followup_change is not None:
            store.update_lead(r['id'], {k: v for k, v in (('status', stage_change), ('next_followup', followup_change)) if v is not None})
        else:
            return False
        self.window.lead_changed(r['id'])
        return True

    def save_and_next(self):
        self.save_current()
        self.go(self.index + 1)

    def go(self, index):
        if index >= len(self.ids):
            return self.finish()
        self.notes_timer.stop()
        self.save_notes()
        self.index = max(0, index)
        self.load()

    def finish(self):
        self.notes_timer.stop()
        self.save_notes()
        counts = {}
        for outcome in self.results.values():
            counts[outcome] = counts.get(outcome, 0) + 1
        summary = ', '.join(f'{n} {o.lower()}' for o, n in sorted(counts.items(), key=lambda x: -x[1]))
        self.window.statusBar().showMessage(f'Call session finished: {plural(len(self.results), "lead")} logged' + (f' ({summary})' if summary else ''), 20000)
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'LeadDock {store.VERSION} — Prospecting CRM')
        self.resize(1500, 880)
        self.setMinimumSize(1100, 640)
        self.setStyleSheet(STYLE)
        self.settings = store.load_settings()
        self.signals = Signals()
        self.signals.bridge_event.connect(self.on_bridge_event)
        self.signals.scan_done.connect(self.on_scan_done)
        self.scanner = WebsiteScanner(self.signals)
        self.helper_status = ''
        self.shown_ids = []

        root = QWidget()
        self.setCentralWidget(root)
        top = QVBoxLayout(root)
        top.setContentsMargins(14, 10, 14, 8)
        top.setSpacing(8)

        header = QHBoxLayout()
        top.addLayout(header)
        brand = QLabel('◈  LeadDock')
        brand.setObjectName('brand')
        header.addWidget(brand)
        self.count = QLabel('')
        self.count.setObjectName('hint')
        header.addSpacing(12)
        header.addWidget(self.count)
        header.addStretch()
        add = QPushButton('+ Add lead')
        add.setObjectName('primary')
        add.clicked.connect(self.add_lead)
        header.addWidget(add)
        for title, handler in [('Import CSV', self.import_csv), ('Export CSV', self.export_csv), ('Connect browser', self.pairing)]:
            b = QPushButton(title)
            b.clicked.connect(handler)
            header.addWidget(b)
        more = QPushButton('More ▾')
        self.more_menu = QMenu(self)
        self.more_menu.addAction('Scan websites of selected leads', lambda: self.scan_ids(self.selected_ids()))
        self.more_menu.addAction('Scan all websites not scanned yet', self.scan_unscanned)
        self.auto_scan = QAction('Automatically scan websites of captured leads', self, checkable=True)
        self.auto_scan.setChecked(bool(self.settings.get('auto_scan_websites', True)))
        self.auto_scan.toggled.connect(self.toggle_auto_scan)
        self.more_menu.addAction(self.auto_scan)
        self.more_menu.addSeparator()
        self.more_menu.addAction('Back up database…', self.backup)
        self.more_menu.addAction('Open data folder', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(store.APP_DIR))))
        self.more_menu.addSeparator()
        self.more_menu.addAction('Exit LeadDock', QApplication.instance().quit)
        more.setMenu(self.more_menu)
        header.addWidget(more)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        top.addWidget(splitter, 1)
        splitter.addWidget(self.build_sidebar())

        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(6, 0, 6, 0)
        cl.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search name, phone, email, website, city, type, notes…   (Ctrl+F)')
        self.search.setClearButtonEnabled(True)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self.search_timer.start(200))
        cl.addWidget(self.search)
        bar = QHBoxLayout()
        cl.addLayout(bar)
        self.filter_label = QLabel('')
        self.filter_label.setObjectName('filters')
        self.filter_label.setTextFormat(Qt.TextFormat.RichText)
        bar.addWidget(self.filter_label, 1)
        self.clear_filters = QPushButton('✕ Clear filters')
        self.clear_filters.setObjectName('link')
        self.clear_filters.clicked.connect(self.reset_filters)
        bar.addWidget(self.clear_filters)
        self.call_button = QPushButton('📞 Call these leads')
        self.call_button.setObjectName('call')
        self.call_button.setToolTip('Work through the leads shown, one at a time: call, pick what happened, next.')
        self.call_button.clicked.connect(lambda: self.start_calls(self.shown_ids))
        bar.addWidget(self.call_button)

        self.tabs = QTabWidget()
        cl.addWidget(self.tabs, 1)
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(30)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        for col, name in enumerate(COLUMNS):
            self.table.setColumnWidth(col, COLUMN_WIDTHS[name])
        for name in self.settings.get('hidden_column_names', HIDDEN_BY_DEFAULT):
            if name in COLUMNS[1:]:
                self.table.setColumnHidden(COLUMNS.index(name), True)
        head.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        head.customContextMenuRequested.connect(self.header_menu)
        head.sectionResized.connect(lambda col, *_: None if col == 0 else QTimer.singleShot(0, self.fit_columns))
        self.table.installEventFilter(self)
        head.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)  # newest activity first until a header is clicked
        head.setSortIndicatorClearable(True)
        self.table.setSortingEnabled(True)
        self.table.itemSelectionChanged.connect(self.selection_changed)
        self.table.itemDoubleClicked.connect(lambda *_: self.details.start_log('Note'))
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self.table_menu)
        self.tabs.addTab(self.table, 'Leads')
        self.pipeline = QTableWidget(0, 4)
        self.pipeline.setHorizontalHeaderLabels(['Stage', 'Leads', 'Deal value', 'Share'])
        self.pipeline.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.pipeline.verticalHeader().hide()
        self.pipeline.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.pipeline.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.pipeline.itemDoubleClicked.connect(self.pipeline_clicked)
        pipe_box = QWidget()
        pl = QVBoxLayout(pipe_box)
        pl.setContentsMargins(0, 6, 0, 0)
        self.pipe_summary = QLabel('')
        self.pipe_summary.setObjectName('hint')
        pl.addWidget(self.pipe_summary)
        pl.addWidget(self.pipeline, 1)
        hint = QLabel('Double-click a stage to see its leads.')
        hint.setObjectName('hint')
        pl.addWidget(hint)
        self.tabs.addTab(pipe_box, 'Pipeline')
        splitter.addWidget(center)
        self.details = LeadDetails(self)
        splitter.addWidget(self.details)
        splitter.setSizes([215, 760, 525])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 2)
        splitter.setCollapsible(1, False)

        QShortcut(QKeySequence('Ctrl+F'), self, lambda: (self.search.setFocus(), self.search.selectAll()))
        QShortcut(QKeySequence('Ctrl+N'), self, self.add_lead)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.refresh)

        self.statusBar().showMessage('Database: ' + str(store.DB_PATH))
        self.refresh()
        self.server = None
        try:
            self.server = bridge.start_server(store.get_key(), lambda kind, lead_id, outcome: self.signals.bridge_event.emit(kind, lead_id, outcome))
        except OSError as e:
            QMessageBox.warning(self, 'LeadDock is already open',
                                f'Port {bridge.PORT} is already in use — LeadDock is probably already open in another window.\n\n{e}')

        self.tray = QSystemTrayIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), self)
        tray_menu = QMenu()
        tray_menu.addAction('Open LeadDock', self.bring_to_front)
        tray_menu.addAction('Exit LeadDock', QApplication.instance().quit)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(lambda reason: self.bring_to_front() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.setToolTip('LeadDock')
        self.tray.show()
        QTimer.singleShot(1500, self.remind_followups)
        # The browser helper writes leads straight into the database, so watch it for changes made outside the app.
        self.db_stamp, self.last_lead_id = store.change_stamp(), max(store.lead_ids_after(0) or [0])
        self.watcher = QTimer(self)
        self.watcher.timeout.connect(self.check_outside_changes)
        self.watcher.start(3000)
        QTimer.singleShot(2500, self.scan_missed_captures)

    # ---------------------------------------------------------------- filter sidebar
    def build_sidebar(self):
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(4)
        self.facets = {}
        for key, title, all_label in [('view', 'SHOW', 'All leads'), ('industry', 'BUSINESS TYPE', 'All types'),
                                      ('stage', 'STAGE', 'All stages'), ('city', 'CITY', 'All cities')]:
            lay.addWidget(section(title))
            facet = FilterList(all_label)
            facet.changed.connect(lambda: QTimer.singleShot(0, self.refresh))  # don't rebuild the list mid-click
            self.facets[key] = facet
            lay.addWidget(facet)
            lay.addSpacing(8)
        lay.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(content)
        scroll.setMinimumWidth(170)
        return scroll

    def filters(self):
        f = {k: facet.key() for k, facet in self.facets.items()}
        return {'search': self.search.text().strip(), 'view': f['view'] or 'All leads', 'stage': f['stage'] or 'All stages',
                'industry': f['industry'], 'city': f['city']}

    def reset_filters(self):
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        for facet in self.facets.values():
            facet.updating = True
            facet.setCurrentRow(0)
            facet.updating = False
        self.refresh()

    def set_filter(self, key, value):
        self.facets[key].set_key(value)

    def refresh_facets(self, f, shown):
        counts = store.facet_counts(**f)
        total = counts['views']['All leads']
        self.facets['view'].set_options([(v, v, counts['views'][v], WARN if v == 'Follow-ups due' and counts['views'][v] else None)
                                         for v in store.VIEWS[1:]], total)
        self.facets['industry'].set_options([(k, k, n, None) for k, n in counts['industries']], sum(n for _, n in counts['industries']))
        self.facets['stage'].set_options([(s, s, n, STAGE_COLORS[s]) for s, n in counts['stages']], sum(n for _, n in counts['stages']))
        self.facets['city'].set_options([(c, c, n, None) for c, n in counts['cities'] if c], sum(n for _, n in counts['cities']))
        everything = store.facet_counts()['views']
        due = everything['Follow-ups due']
        self.count.setText(f"{plural(everything['All leads'], 'lead')}" + (f"  ·  {due} follow-up{'s' if due != 1 else ''} due" if due else ''))
        active = [x for x in (f['industry'], f['stage'] if f['stage'] in STAGES else '', f['city'],
                              f['view'] if f['view'] != 'All leads' else '', f'“{f["search"]}”' if f['search'] else '') if x]
        self.filter_label.setText(f'<b>{shown:,}</b> of {everything["All leads"]:,} leads' +
                                  (' &nbsp;·&nbsp; ' + ' &nbsp;·&nbsp; '.join(html.escape(a) for a in active) if active else ''))
        self.clear_filters.setVisible(bool(active))

    # ---------------------------------------------------------------- list
    def eventFilter(self, obj, event):
        if obj is self.table and event.type() == event.Type.Resize:
            QTimer.singleShot(0, self.fit_columns)
        return super().eventFilter(obj, event)

    def fit_columns(self):
        """The Business column takes whatever room the other columns leave (but never gets unreadably narrow)."""
        others = sum(self.table.columnWidth(c) for c in range(1, self.table.columnCount()) if not self.table.isColumnHidden(c))
        self.table.setColumnWidth(0, max(190, self.table.viewport().width() - others))

    def header_menu(self, pos):
        menu = QMenu(self)
        for col, name in enumerate(COLUMNS[1:], start=1):
            act = menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(not self.table.isColumnHidden(col))
            act.toggled.connect(lambda on, col=col: self.set_column_visible(col, on))
        menu.exec(self.table.horizontalHeader().mapToGlobal(pos))

    def set_column_visible(self, col, on):
        self.table.setColumnHidden(col, not on)
        self.settings['hidden_column_names'] = [n for c, n in enumerate(COLUMNS) if self.table.isColumnHidden(c)]
        store.save_settings(self.settings)
        self.fit_columns()

    def selected_ids(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows if self.table.item(r, 0)]

    def displayed_ids(self):
        return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in range(self.table.rowCount())]

    def refresh(self, *_):
        selected = self.details.lead_id if hasattr(self, 'details') else None
        f = self.filters()
        rows = store.query_leads(**f)
        self.refresh_facets(f, len(rows))

        scroll = self.table.verticalScrollBar().value()
        self.table.blockSignals(True)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        today = date.today().isoformat()
        select_row = None
        for i, r in enumerate(rows):
            name = SortItem(r['name'])
            name.setData(Qt.ItemDataRole.UserRole, r['id'])
            name.setToolTip('\n'.join(x for x in (r['category'], r['address'], r['notes'][:200] if r['notes'] else '') if x))
            kind = SortItem(r['industry'] or 'Other')
            kind.setToolTip(r['category'] or '')
            stage = SortItem(r['status'] or 'New', STAGES.index(r['status']) if r['status'] in STAGES else 0)
            stage.setForeground(QColor(STAGE_COLORS.get(r['status'], '#c9d3e6')))
            prio = SortItem(r['priority'] or 'Normal', PRIORITIES.index(r['priority']) if r['priority'] in PRIORITIES else 1)
            prio.setForeground(QColor(PRIORITY_COLORS.get(r['priority'], '#c9d3e6')))
            if r['website']:
                site = SortItem(store.site_domain(r['website']) + ('  ⚠' if r['website_issues'] else ''))
                site.setToolTip(r['website_issues'] or r['website'])
                if r['website_issues']:
                    site.setForeground(QColor(HOT))
            else:
                site = SortItem('— no website', '')
                site.setForeground(QColor(HOT))
            try:
                rating_key = float(r['rating'] or 0)
            except ValueError:
                rating_key = 0.0
            reviews = int(r['review_count']) if (r['review_count'] or '').isdigit() else None
            count = '' if reviews is None else f'  ({reviews / 1000:.1f}k)' if reviews >= 1000 else f'  ({reviews})'
            rating = SortItem(f"★ {r['rating']}{count}" if r['rating'] else '', rating_key)
            if reviews is not None:
                rating.setToolTip(f'{reviews:,} Google reviews')
            due = r['next_followup'] or ''
            follow = SortItem(store.followup_label(due), due or '9999')
            if due and due <= today and r['status'] not in store.CLOSED_STAGES:
                follow.setForeground(QColor(WARN))
            note = SortItem(' '.join((r['last_note'] or '').split()))
            note.setToolTip(r['last_note'] or '')
            note.setForeground(QColor('#aab6cc'))
            contacted = SortItem(nice_date(r['last_contacted']) or 'Never', r['last_contacted'] or '')
            if not r['last_contacted']:
                contacted.setForeground(QColor(MUTED))
            city = ', '.join(x for x in (r['city'], r['state']) if x)
            cells = {'Business': name, 'Type': kind, 'Stage': stage, 'Phone': SortItem(r['phone'] or ''), 'Follow-up': follow,
                     'Last note': note, 'Website': site, 'City': SortItem(city), 'Rating': rating, 'Priority': prio, 'Last contact': contacted}
            for j, column in enumerate(COLUMNS):
                self.table.setItem(i, j, cells[column])
            if r['id'] == selected:
                select_row = i
        self.table.setSortingEnabled(True)
        self.table.blockSignals(False)
        if select_row is not None:
            for i in range(self.table.rowCount()):  # sorting may have moved it
                if self.table.item(i, 0).data(Qt.ItemDataRole.UserRole) == selected:
                    self.table.blockSignals(True)
                    self.table.selectRow(i)
                    self.table.blockSignals(False)
                    break
        self.table.verticalScrollBar().setValue(scroll)
        self.shown_ids = self.displayed_ids()
        callable_count = sum(1 for r in rows if r['phone'])
        self.call_button.setText(f'📞 Call these {callable_count:,}' if callable_count else '📞 Call these leads')
        self.call_button.setEnabled(bool(callable_count))
        self.refresh_pipeline()
        self.db_stamp = store.change_stamp()

    def refresh_pipeline(self):
        stages, total, _ = store.pipeline_summary()
        self.pipeline.setRowCount(len(stages))
        for i, (stage, n, value) in enumerate(stages):
            cells = [stage, str(n), '${:,.0f}'.format(value or 0), f'{(n / total * 100) if total else 0:.0f}%']
            for j, v in enumerate(cells):
                item = QTableWidgetItem(v)
                if j == 0:
                    item.setForeground(QColor(STAGE_COLORS[stage]))
                self.pipeline.setItem(i, j, item)
        by = {s: (n, v) for s, n, v in stages}
        open_value = sum(v for s, (n, v) in by.items() if s not in store.CLOSED_STAGES)
        won, lost = by['Won'][0], by['Lost'][0]
        rate = f'{won / (won + lost) * 100:.0f}%' if won + lost else '—'
        self.pipe_summary.setText(f"Open pipeline: ${open_value:,.0f}   ·   Won: ${by['Won'][1]:,.0f} ({plural(won, 'deal')})   ·   Win rate: {rate}")

    def pipeline_clicked(self, item):
        self.set_filter('stage', self.pipeline.item(item.row(), 0).text())
        self.tabs.setCurrentIndex(0)

    def selection_changed(self):
        ids = self.selected_ids()
        if len(ids) == 1 and ids[0] != self.details.lead_id:
            self.details.set_lead(store.get_lead(ids[0]))
        elif len(ids) > 1:
            self.statusBar().showMessage(f'{len(ids)} leads selected — right-click for bulk actions', 5000)

    def select_id(self, lead_id, reveal=True):
        for i in range(self.table.rowCount()):
            if self.table.item(i, 0).data(Qt.ItemDataRole.UserRole) == lead_id:
                self.table.selectRow(i)
                self.table.scrollToItem(self.table.item(i, 0))
                return True
        if reveal:  # not visible under the current filters
            self.reset_filters()
            return self.select_id(lead_id, reveal=False)
        return False

    def lead_changed(self, lead_id):
        self.refresh_timer.start(250)

    def table_menu(self, pos):
        ids = self.selected_ids()
        if not ids:
            return
        menu = QMenu(self)
        if len(ids) > 1:
            menu.addAction(f'📞 Call these {len(ids)} leads', lambda: self.start_calls(ids))
            menu.addSeparator()
        stage_menu = menu.addMenu('Set stage')
        for s in STAGES:
            stage_menu.addAction(s, lambda checked=False, s=s: self.bulk_update(ids, {'status': s}))
        type_menu = menu.addMenu('Set business type')
        for t in store.industries_in_use():
            type_menu.addAction(t, lambda checked=False, t=t: self.bulk_update(ids, {'industry': t}))
        type_menu.addSeparator()
        type_menu.addAction('Custom type…', lambda: self.custom_type(ids))
        prio_menu = menu.addMenu('Set priority')
        for p in PRIORITIES:
            prio_menu.addAction(p, lambda checked=False, p=p: self.bulk_update(ids, {'priority': p}))
        first = store.get_lead(ids[0])
        follow = followup_menu(self, first['next_followup'] if first else '', lambda d: self.bulk_update(ids, {'next_followup': d}))
        follow.setTitle('Follow-up')
        menu.addMenu(follow)
        if len(ids) == 1:
            outcome_menu = menu.addMenu('Log call outcome')
            for o in store.CALL_OUTCOMES:
                outcome_menu.addAction(o, lambda checked=False, o=o: self.details.log_outcome(o))
            for kind in ('Note', 'Email', 'Visit'):
                menu.addAction(f'Log {kind.lower()}…', lambda checked=False, k=kind: self.details.start_log(k))
            menu.addSeparator()
            if first['phone']:
                menu.addAction(f"📞 Call {first['phone']}", lambda: dial(first['phone']))
                menu.addAction(f"Copy phone  {first['phone']}", lambda: self.details.copy('phone'))
            menu.addAction('Open in Google Maps', lambda: self.details.buttons['maps'].click())
            if first['website']:
                menu.addAction('Open website', lambda: self.details.open_url(first['website']))
        menu.addSeparator()
        menu.addAction(f'Scan website{"s" if len(ids) > 1 else ""}', lambda: self.scan_ids(ids))
        menu.addAction(f'Export {len(ids)} selected to CSV…', lambda: self.export_csv(ids))
        menu.addAction(f'Delete {plural(len(ids), "lead")}…', lambda: self.delete_ids(ids))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def custom_type(self, ids):
        text, ok = QInputDialog.getText(self, 'Business type', 'Type for the selected leads:')
        if ok and text.strip():
            self.bulk_update(ids, {'industry': text.strip()})

    def bulk_update(self, ids, changes):
        for lead_id in ids:
            store.update_lead(lead_id, changes)
        self.refresh()
        self.details.reload()
        self.statusBar().showMessage(f'Updated {plural(len(ids), "lead")}', 4000)

    def delete_ids(self, ids):
        ids = [i for i in ids if i]
        if not ids:
            return
        label = store.get_lead(ids[0])['name'] if len(ids) == 1 else f'{len(ids)} leads'
        if QMessageBox.question(self, 'Delete', f'Permanently delete {label} and its timeline?') != QMessageBox.StandardButton.Yes:
            return
        store.delete_leads(ids)
        if self.details.lead_id in ids:
            self.details.pending = {}
            self.details.set_lead(None)
        self.refresh()

    # ---------------------------------------------------------------- call session
    def start_calls(self, ids):
        rows = [store.get_lead(i) for i in ids]
        callable_ids = [r['id'] for r in rows if r and r['phone']]
        if not callable_ids:
            QMessageBox.information(self, 'Call session', 'None of these leads has a phone number.')
            return
        f = self.filters()
        title = ' · '.join(x for x in (f['industry'], f['stage'] if f['stage'] in STAGES else '', f['city'],
                                       f['view'] if f['view'] != 'All leads' else '') if x) or 'your leads'
        if ids is not self.shown_ids:
            title = plural(len(callable_ids), 'selected lead')
        self.details.save_pending()
        CallSession(self, callable_ids, f'{title} ({len(callable_ids)})').exec()
        self.refresh()
        self.details.reload()

    # ---------------------------------------------------------------- browser bridge & scanning
    def on_bridge_event(self, kind, lead_id, outcome):
        if kind == 'focus':
            self.bring_to_front()
            self.select_id(lead_id)
            return
        self.refresh()
        row = store.get_lead(lead_id)
        if not row:
            return
        if self.details.lead_id == lead_id:
            self.details.reload()
        elif kind == 'capture' and not self.table.selectedIndexes():
            self.select_id(lead_id, reveal=False)
        if kind == 'capture':
            self.announce_capture(row, 'added' if outcome == 'created' else 'updated')

    def announce_capture(self, row, verb):
        self.statusBar().showMessage(f"{row['name']} {verb} from the browser — filed under {row['industry'] or 'Other'}", 8000)
        if self.isHidden() or self.isMinimized():
            self.tray.showMessage('LeadDock', f"{row['name']} {verb}", QSystemTrayIcon.MessageIcon.Information, 2500)
        if self.auto_scan.isChecked() and row['website'] and not row['website_scanned_at']:
            self.scanner.add(row['id'])

    def check_outside_changes(self):
        """Pick up leads the browser helper saved while this window is open."""
        try:
            stamp = store.change_stamp()
        except sqlite3.Error:
            return
        if stamp == self.db_stamp:
            return
        new_ids = store.lead_ids_after(self.last_lead_id)
        self.last_lead_id = max([self.last_lead_id] + new_ids)
        self.refresh()
        self.details.reload()
        for lead_id in new_ids:
            row = store.get_lead(lead_id)
            if row and (row['source'] or '').startswith('Google'):
                self.announce_capture(row, 'added')
        if len(new_ids) == 1 and not self.table.selectedIndexes():
            self.select_id(new_ids[0], reveal=False)

    def scan_missed_captures(self):
        """Scan websites of leads that were captured while LeadDock was closed."""
        if self.auto_scan.isChecked():
            ids = store.unscanned_captures()
            if ids:
                self.scan_ids(ids)

    def scan_ids(self, ids):
        ids = list(ids)
        for lead_id in ids:
            self.scanner.add(lead_id)
        if ids:
            self.statusBar().showMessage(f'Scanning {plural(len(ids), "website")} in the background…')

    def scan_unscanned(self):
        rows = [r['id'] for r in store.query_leads() if r['website'] and not r['website_scanned_at']]
        if not rows:
            QMessageBox.information(self, 'Website scan', 'Every lead with a website has already been scanned.')
            return
        if QMessageBox.question(self, 'Website scan', f'Scan {len(rows)} websites now? This runs in the background and only visits each business’s own site.') == QMessageBox.StandardButton.Yes:
            self.scan_ids(rows)

    def on_scan_done(self, lead_id, message):
        if message:
            self.statusBar().showMessage(message + (f'  ·  {len(self.scanner.pending)} left' if self.scanner.pending else ''), 10000)
        if self.details.lead_id == lead_id:
            self.details.reload()
        self.refresh_timer.start(400)

    def toggle_auto_scan(self, on):
        self.settings['auto_scan_websites'] = on
        store.save_settings(self.settings)

    # ---------------------------------------------------------------- toolbar actions
    def add_lead(self):
        lead_id, _, _ = store.store_lead({'name': 'New business ' + datetime.now().strftime('%H:%M:%S'), 'source': 'Manual'})
        self.select_id(lead_id)
        self.details.set_lead(store.get_lead(lead_id))
        self.details.tabs.setCurrentIndex(1)
        name = self.details.fields['name']
        name.setFocus()
        name.selectAll()

    def export_csv(self, ids=None):
        if ids:
            rows = [store.get_lead(i) for i in ids]
        else:
            rows = store.query_leads(**self.filters())
        target, _ = QFileDialog.getSaveFileName(self, f'Export {len(rows)} leads', str(Path.home() / f'leaddock_leads_{date.today().isoformat()}.csv'), 'CSV files (*.csv)')
        if target:
            n = store.export_csv(target, [r for r in rows if r])
            QMessageBox.information(self, 'Export complete', f'Exported {n} leads to\n{target}')

    def import_csv(self):
        source, _ = QFileDialog.getOpenFileName(self, 'Import leads', '', 'CSV files (*.csv)')
        if not source:
            return
        created, updated, skipped = store.import_csv(source)
        self.refresh()
        QMessageBox.information(self, 'Import complete', f'New leads: {created}\nUpdated existing leads: {updated}\nSkipped rows: {skipped}')

    def backup(self):
        target, _ = QFileDialog.getSaveFileName(self, 'Back up database', str(Path.home() / f'LeadDock_backup_{date.today().isoformat()}.sqlite3'), 'SQLite Database (*.sqlite3)')
        if target:
            src, dest = sqlite3.connect(store.DB_PATH), sqlite3.connect(target)
            try:
                src.backup(dest)
            finally:
                src.close()
                dest.close()
            QMessageBox.information(self, 'Backup created', 'Saved database backup to:\n' + target)

    def pairing(self):
        key = store.get_key()
        d = QDialog(self)
        d.setWindowTitle('Connect your browser')
        d.setMinimumWidth(620)
        d.setStyleSheet(STYLE)
        layout = QVBoxLayout(d)
        helper = QLabel(chip(self.helper_status, GOOD if self.helper_status.startswith('Browser helper installed') else HOT))
        helper.setTextFormat(Qt.TextFormat.RichText)
        helper.setWordWrap(True)
        layout.addWidget(helper)
        info = QLabel('1. In Edge open <b>edge://extensions</b> (Chrome: <b>chrome://extensions</b>) and turn on <b>Developer mode</b>.<br>'
                      '2. If an older LeadDock extension is listed, click <b>Remove</b> on it first.<br>'
                      '3. Click <b>Load unpacked</b> and choose the <b>LeadDock-2.0\\extension</b> folder.<br>'
                      '4. Open any business in Google Maps (or a business profile in Google Search) and click the LeadDock icon '
                      '(or press <b>Alt+Shift+L</b>). The pill at the top should say <b>Ready</b>.<br><br>'
                      'Leads save straight into LeadDock — this app does <b>not</b> need to be open.')
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setWordWrap(True)
        layout.addWidget(info)
        msg = QLabel('Pairing key — only needed if your PC blocks the browser helper (then paste it under ⚙ in the extension, '
                     'and leads save while this app is open):')
        msg.setObjectName('hint')
        msg.setWordWrap(True)
        layout.addWidget(msg)
        field = QLineEdit(key)
        field.setReadOnly(True)
        layout.addWidget(field)
        b = QPushButton('Copy pairing key')
        b.clicked.connect(lambda: (QApplication.clipboard().setText(key), b.setText('✓ Copied')))
        layout.addWidget(b)
        d.exec()

    def remind_followups(self):
        due = store.view_counts()['Follow-ups due']
        if due:
            self.statusBar().showMessage(f'{plural(due, "follow-up")} due — click “Follow-ups due” on the left.', 15000)
            self.tray.showMessage('LeadDock', f'{plural(due, "follow-up")} due today', QSystemTrayIcon.MessageIcon.Information, 4000)

    def bring_to_front(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        # The browser extension saves through its helper, so closing the window simply quits.
        self.details.save_pending()
        self.tray.hide()
        event.accept()
        QApplication.instance().quit()


def main():
    store.init_db()
    try:  # (re)register the browser helper so the extension can save while this app is closed
        import native_host
        helper_status = native_host.install()
    except Exception as e:
        helper_status = f'Browser helper could not be installed ({e}). Leads still save while LeadDock is open.'
    app = QApplication(sys.argv)
    app.setApplicationName('LeadDock')
    window = MainWindow()
    window.helper_status = helper_status
    window.statusBar().showMessage(helper_status + f'  ·  Database: {store.DB_PATH}', 15000)
    window.showMaximized()
    if '--select' in sys.argv:  # "Open in LeadDock" from the extension
        try:
            lead_id = int(sys.argv[sys.argv.index('--select') + 1])
            QTimer.singleShot(400, lambda: (window.select_id(lead_id), window.bring_to_front()))
        except (IndexError, ValueError):
            pass
    app.aboutToQuit.connect(window.details.save_pending)
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
