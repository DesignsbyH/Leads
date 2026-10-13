"""LeadDock — local-first prospecting CRM. Python 3.10+ / PySide6."""
import html, queue, sqlite3, sys, threading
from datetime import date, datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QUrl, QDate
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QLineEdit, QPlainTextEdit, QComboBox, QTableWidget, QTableWidgetItem, QSplitter, QFormLayout,
    QFileDialog, QMessageBox, QTabWidget, QHeaderView, QSystemTrayIcon, QMenu, QStyle, QFrame, QAbstractItemView,
    QDialog, QScrollArea, QTextBrowser, QCalendarWidget, QDialogButtonBox, QSizePolicy)

import bridge, enrich, store
from store import STAGES, PRIORITIES, ACTIVITY_TYPES

STAGE_COLORS = {'New': '#8b9bff', 'Qualified': '#45c8e6', 'Contacted': '#f5bd4f', 'Follow Up': '#ff9b45',
                'Proposal': '#b993ff', 'Won': '#4fd68f', 'Lost': '#8a94a6'}
PRIORITY_COLORS = {'Low': '#8a94a6', 'Normal': '#c9d3e6', 'High': '#ffb15c', 'Urgent': '#ff6b6b'}
ACTION_COLORS = {'Note': '#c9d3e6', 'Call': '#6fd3a6', 'Email': '#7fb2ff', 'Text': '#7fb2ff', 'Visit': '#f5bd4f',
                 'Meeting': '#b993ff', 'Stage': '#ff9b45', 'Priority': '#ff9b45', 'Follow-up': '#ff9b45',
                 'Captured': '#8b9bff', 'Refreshed': '#8b9bff', 'Website scan': '#45c8e6'}
WARN, HOT, MUTED, GOOD = '#ff6b6b', '#ffb15c', '#7d8aa3', '#4fd68f'
USER_ACTIONS = set(ACTIVITY_TYPES)  # timeline entries you typed yourself can be deleted

STYLE = '''
QWidget { background:#0d111b; color:#e9edf7; font-family:'Segoe UI'; font-size:12px; }
QMainWindow, QDialog { background:#0d111b; }
QLabel#heading { font-size:21px; font-weight:700; } QLabel#brand { font-size:20px; font-weight:700; }
QLabel#hint { color:#93a0b8; } QLabel#section { color:#8ea0c2; font-size:11px; font-weight:700; letter-spacing:1px; }
QFrame#panel { background:#151b2a; border:1px solid #293248; border-radius:12px; }
QLineEdit, QPlainTextEdit, QComboBox, QTextBrowser { background:#121929; border:1px solid #303a50; border-radius:7px; padding:6px; selection-background-color:#4364db; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border:1px solid #6e8df9; }
QLineEdit:read-only { color:#93a0b8; }
QComboBox QAbstractItemView { background:#151b2a; border:1px solid #303a50; selection-background-color:#34446b; }
QPushButton { background:#252e43; border:1px solid #35415a; border-radius:7px; padding:7px 11px; font-weight:600; }
QPushButton:hover { background:#34425e; } QPushButton:disabled { color:#5d6880; }
QPushButton#primary { background:#566ff0; border:0; color:white; } QPushButton#primary:hover { background:#7189ff; }
QPushButton#danger { background:#3a1f27; border:1px solid #5a2a36; color:#ffb3bd; }
QTableWidget { background:#121929; alternate-background-color:#161f33; gridline-color:#1f293d; border:1px solid #283247; border-radius:8px; }
QHeaderView::section { background:#1c2538; color:#b5c1d6; border:0; padding:8px; font-weight:600; }
QTableWidget::item { padding:4px; } QTableWidget::item:selected { background:#34446b; color:white; }
QTabWidget::pane { border:0; } QTabBar::tab { padding:8px 14px; background:#182032; margin-right:5px; border-radius:7px; }
QTabBar::tab:selected { background:#4057b1; } QSplitter::handle { background:#1c2538; }
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
    """Quick follow-up choices shared by the details panel and the table's right-click menu."""
    menu = QMenu(parent)
    for label, days in [('Today', 0), ('Tomorrow', 1), ('In 3 days', 3), ('Next week', 7), ('In 2 weeks', 14), ('In a month', 30)]:
        menu.addAction(f"{label}  ({nice_date(store.quick_date(days))})", lambda checked=False, d=days: apply(store.quick_date(d)))

    def pick():
        dialog = DatePickDialog(parent, current)
        if dialog.exec():
            apply(dialog.value())
    menu.addAction('Pick a date…', pick)
    menu.addSeparator()
    menu.addAction('Clear follow-up', lambda: apply(''))
    return menu


class LeadDetails(QWidget):
    """Right-hand panel: quick pipeline controls, notes & activity timeline, business info, website audit."""

    def __init__(self, window):
        super().__init__()
        self.window, self.lead_id, self.row, self.loading, self.pending = window, None, None, False, {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 4, 4, 8)
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

        quick = QGridLayout()
        quick.setHorizontalSpacing(8)
        lay.addLayout(quick)
        self.stage = QComboBox()
        self.stage.addItems(STAGES)
        self.stage.currentTextChanged.connect(lambda v: self.set_pipeline({'status': v}))
        self.priority = QComboBox()
        self.priority.addItems(PRIORITIES)
        self.priority.currentTextChanged.connect(lambda v: self.set_pipeline({'priority': v}))
        self.followup = QPushButton('Set follow-up ▾')
        self.followup.clicked.connect(self.followup_clicked)
        for col, (label, widget) in enumerate([('STAGE', self.stage), ('PRIORITY', self.priority), ('FOLLOW-UP', self.followup)]):
            head = QLabel(label)
            head.setObjectName('section')
            quick.addWidget(head, 0, col)
            quick.addWidget(widget, 1, col)

        links = QHBoxLayout()
        lay.addLayout(links)
        self.buttons = {}
        for key, text, handler in [('maps', '↗ Maps', lambda: self.open_url(self.row['maps_url'] or store.maps_search_url(self.row['name'], self.row['address']))),
                                   ('web', '↗ Website', lambda: self.open_url(self.row['website'])),
                                   ('phone', 'Copy phone', lambda: self.copy('phone')),
                                   ('email', 'Copy email', lambda: self.copy('email')),
                                   ('scan', 'Scan website', self.scan)]:
            b = QPushButton(text)
            b.clicked.connect(handler)
            links.addWidget(b)
            self.buttons[key] = b

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
        head = QLabel('PINNED NOTES')
        head.setObjectName('section')
        lay.addWidget(head)
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText('Always-visible summary: decision maker, what they need, objections, pricing discussed…')
        self.notes.setMaximumHeight(84)
        self.notes.textChanged.connect(lambda: self.queue_save('notes', self.notes.toPlainText()))
        lay.addWidget(self.notes)

        head = QLabel('LOG ACTIVITY')
        head.setObjectName('section')
        lay.addWidget(head)
        row = QHBoxLayout()
        lay.addLayout(row)
        self.note_type = QComboBox()
        self.note_type.addItems(ACTIVITY_TYPES)
        self.composer = QPlainTextEdit()
        self.composer.setPlaceholderText('What happened? e.g. "Spoke with owner Mike — call back Thursday with a quote."  (Ctrl+Enter to add)')
        self.composer.setMaximumHeight(62)
        self.add_button = QPushButton('Add')
        self.add_button.setObjectName('primary')
        self.add_button.clicked.connect(self.add_activity)
        side = QVBoxLayout()
        side.addWidget(self.note_type)
        side.addWidget(self.add_button)
        row.addWidget(self.composer, 1)
        row.addLayout(side)
        for keys in ('Ctrl+Return', 'Ctrl+Enter'):
            QShortcut(QKeySequence(keys), self.composer, self.add_activity, context=Qt.ShortcutContext.WidgetShortcut)

        head = QLabel('TIMELINE')
        head.setObjectName('section')
        lay.addWidget(head)
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
        head = QLabel('WEBSITE AUDIT')
        head.setObjectName('section')
        lay.addWidget(head)
        self.audit = QPlainTextEdit()
        self.audit.setReadOnly(True)
        self.audit.setPlaceholderText('Scan the website to check HTTPS, mobile-friendliness, platform, copyright year and find emails/social links.')
        lay.addWidget(self.audit, 1)
        head = QLabel('SOCIAL LINKS (one per line)')
        head.setObjectName('section')
        lay.addWidget(head)
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
        for w in [self.stage, self.priority, self.followup, self.tabs, self.delete, *self.buttons.values()]:
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
            self.loading = False
            return
        self.title.setText(row['name'])
        self.refresh_header()
        self.stage.setCurrentText(row['status'] if row['status'] in STAGES else 'New')
        self.priority.setCurrentText(row['priority'] if row['priority'] in PRIORITIES else 'Normal')
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
        self.buttons['web'].setEnabled(bool(row['website']))
        self.buttons['phone'].setEnabled(bool(row['phone']))
        self.buttons['email'].setEnabled(bool(row['email']))
        self.load_website(row)
        self.load_timeline()
        self.saved.setText('Changes save automatically')
        self.loading = False

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
            delete = f' &nbsp;<a href="delete:{a["id"]}" style="color:#5d6880; text-decoration:none">✕</a>' if a['action'] in USER_ACTIONS else ''
            detail = html.escape(a['detail'] or '').replace('\n', '<br>')
            parts.append(f'<div style="margin-bottom:9px"><span style="color:{color}; font-weight:700">{html.escape(a["action"])}</span>'
                         f'<span style="color:#7d8aa3"> &nbsp;·&nbsp; {nice_time(a["at"])}</span>{delete}<br>{detail}</div>')
        self.timeline.setHtml(''.join(parts) or '<span style="color:#7d8aa3">No activity yet.</span>')

    def reload(self):
        if self.lead_id:
            row = store.get_lead(self.lead_id)
            focus = QApplication.focusWidget()
            if row and focus in (self.notes, self.socials, self.composer, *self.fields.values()):
                # Don't yank text out from under the user; just refresh the read-only parts.
                self.row = row
                self.refresh_header()
                self.load_timeline()
                self.update_followup_button()
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
        self.refresh_header()
        self.buttons['web'].setEnabled(bool(self.row['website']))
        self.buttons['phone'].setEnabled(bool(self.row['phone']))
        self.buttons['email'].setEnabled(bool(self.row['email']))
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

    def update_followup_button(self):
        due = (self.row['next_followup'] if self.row else '') or ''
        label = store.followup_label(due)
        if not label:
            text = 'Set follow-up ▾'
        elif label.startswith(('Overdue', 'Today', 'Tomorrow')):
            text = f'{label} · {nice_date(due)} ▾'
        else:
            text = f'{label} ▾'
        self.followup.setText(text)
        self.followup.setStyleSheet(f'color:{WARN};' if due and due <= date.today().isoformat() else '')

    def followup_clicked(self):
        menu = followup_menu(self, self.row['next_followup'], lambda d: self.set_pipeline({'next_followup': d}))
        menu.exec(self.followup.mapToGlobal(self.followup.rect().bottomLeft()))

    def add_activity(self):
        if not self.lead_id:
            return
        text, kind = self.composer.toPlainText().strip(), self.note_type.currentText()
        try:
            extra = store.add_activity(self.lead_id, kind, text)
        except ValueError as e:
            self.saved.setText('⚠ ' + str(e))
            return
        self.composer.clear()
        self.note_type.setCurrentText('Note')
        self.loading = True
        self.row = store.get_lead(self.lead_id)
        self.stage.setCurrentText(self.row['status'])
        self.loading = False
        self.refresh_header()
        self.load_timeline()
        self.saved.setText(f'✓ {kind} logged' + (' · stage moved to Contacted' if extra.get('status') else ''))
        self.window.lead_changed(self.lead_id)

    def start_log(self, kind):
        self.tabs.setCurrentIndex(0)
        self.note_type.setCurrentText(kind)
        self.composer.setFocus()

    def timeline_link(self, url):
        target = url.toString()
        if target.startswith('delete:') and QMessageBox.question(self, 'Delete entry', 'Delete this timeline entry?') == QMessageBox.StandardButton.Yes:
            store.delete_activity(int(target.split(':')[1]))
            self.load_timeline()

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'LeadDock {store.VERSION} — Prospecting CRM')
        self.resize(1440, 860)
        self.setMinimumSize(980, 600)
        self.setStyleSheet(STYLE)
        self.settings = store.load_settings()
        self.signals = Signals()
        self.signals.bridge_event.connect(self.on_bridge_event)
        self.signals.scan_done.connect(self.on_scan_done)
        self.scanner = WebsiteScanner(self.signals)
        self.helper_status = ''

        root = QWidget()
        self.setCentralWidget(root)
        top = QVBoxLayout(root)
        top.setContentsMargins(16, 12, 16, 10)
        top.setSpacing(9)

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

        bar = QHBoxLayout()
        top.addLayout(bar)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Search name, phone, email, website, city, category, notes…   (Ctrl+F)')
        self.search.setClearButtonEnabled(True)
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda: self.search_timer.start(200))
        bar.addWidget(self.search, 4)
        self.view = QComboBox()
        for v in store.VIEWS:
            self.view.addItem(v, v)
        self.view.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.view, 2)
        self.stage_filter = QComboBox()
        self.stage_filter.addItems(['All stages'] + STAGES)
        self.stage_filter.currentTextChanged.connect(self.refresh)
        bar.addWidget(self.stage_filter, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        top.addWidget(splitter, 1)
        self.tabs = QTabWidget()
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(['Business', 'Stage', 'Follow-up', 'Phone', 'Website', 'Rating', 'City', 'Priority', 'Last contact'])
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
        for col, width in enumerate([220, 84, 96, 110, 145, 96, 110, 66, 84]):
            self.table.setColumnWidth(col, width)
        for col in self.settings.get('hidden_columns', []):
            if 0 < col < self.table.columnCount():
                self.table.setColumnHidden(col, True)
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
        splitter.addWidget(self.tabs)
        self.details = LeadDetails(self)
        splitter.addWidget(self.details)
        splitter.setSizes([900, 540])
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

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
            self.statusBar().showMessage(f'Browser capture ready (127.0.0.1:{bridge.PORT})  ·  Database: {store.DB_PATH}')
        except OSError as e:
            QMessageBox.warning(self, 'Capture service unavailable',
                                f'Port {bridge.PORT} is already in use — LeadDock is probably already running (check the system tray).\n\n{e}')

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
        for col in range(1, self.table.columnCount()):
            act = menu.addAction(self.table.horizontalHeaderItem(col).text())
            act.setCheckable(True)
            act.setChecked(not self.table.isColumnHidden(col))
            act.toggled.connect(lambda on, col=col: self.set_column_visible(col, on))
        menu.exec(self.table.horizontalHeader().mapToGlobal(pos))

    def set_column_visible(self, col, on):
        self.table.setColumnHidden(col, not on)
        self.settings['hidden_columns'] = [c for c in range(self.table.columnCount()) if self.table.isColumnHidden(c)]
        store.save_settings(self.settings)
        self.fit_columns()

    def selected_ids(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows if self.table.item(r, 0)]

    def refresh(self, *_):
        selected = self.details.lead_id if hasattr(self, 'details') else None
        rows = store.query_leads(self.search.text().strip(), self.stage_filter.currentText(), self.view.currentData() or 'All leads')
        counts = store.view_counts()
        for i in range(self.view.count()):
            name = self.view.itemData(i)
            self.view.setItemText(i, name if name == 'All leads' else f'{name} ({counts.get(name, 0)})')
        due = counts['Follow-ups due']
        self.count.setText(f"{counts['All leads']} leads  ·  {len(rows)} shown" + (f"  ·  {due} follow-up{'s' if due != 1 else ''} due" if due else ''))

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
            contacted = SortItem(nice_date(r['last_contacted']) or 'Never', r['last_contacted'] or '')
            if not r['last_contacted']:
                contacted.setForeground(QColor(MUTED))
            city = ', '.join(x for x in (r['city'], r['state']) if x)
            for j, item in enumerate([name, stage, follow, SortItem(r['phone'] or ''), site, rating, SortItem(city), prio, contacted]):
                self.table.setItem(i, j, item)
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
        self.pipe_summary.setText(f"Open pipeline: ${open_value:,.0f}   ·   Won: ${by['Won'][1]:,.0f} ({won} deal{'s' if won != 1 else ''})   ·   Win rate: {rate}")

    def pipeline_clicked(self, item):
        self.stage_filter.setCurrentText(self.pipeline.item(item.row(), 0).text())
        self.view.setCurrentIndex(0)
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
            self.search.clear()
            self.stage_filter.setCurrentIndex(0)
            self.view.setCurrentIndex(0)
            self.refresh()
            return self.select_id(lead_id, reveal=False)
        return False

    def lead_changed(self, lead_id):
        self.refresh_timer.start(250)

    def table_menu(self, pos):
        ids = self.selected_ids()
        if not ids:
            return
        menu = QMenu(self)
        stage_menu = menu.addMenu('Set stage')
        for s in STAGES:
            stage_menu.addAction(s, lambda checked=False, s=s: self.bulk_update(ids, {'status': s}))
        prio_menu = menu.addMenu('Set priority')
        for p in PRIORITIES:
            prio_menu.addAction(p, lambda checked=False, p=p: self.bulk_update(ids, {'priority': p}))
        first = store.get_lead(ids[0])
        follow = followup_menu(self, first['next_followup'] if first else '', lambda d: self.bulk_update(ids, {'next_followup': d}))
        follow.setTitle('Follow-up')
        menu.addMenu(follow)
        if len(ids) == 1:
            menu.addSeparator()
            for kind in ('Note', 'Call', 'Email', 'Visit'):
                menu.addAction(f'Log {kind.lower()}…', lambda checked=False, k=kind: self.details.start_log(k))
            menu.addSeparator()
            menu.addAction('Open in Google Maps', lambda: self.details.buttons['maps'].click())
            if first['website']:
                menu.addAction('Open website', lambda: self.details.open_url(first['website']))
            if first['phone']:
                menu.addAction(f"Copy phone  {first['phone']}", lambda: self.details.copy('phone'))
        menu.addSeparator()
        menu.addAction(f'Scan website{"s" if len(ids) > 1 else ""}', lambda: self.scan_ids(ids))
        menu.addAction(f'Export {len(ids)} selected to CSV…', lambda: self.export_csv(ids))
        menu.addAction(f'Delete {len(ids)} lead{"s" if len(ids) > 1 else ""}…', lambda: self.delete_ids(ids))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def bulk_update(self, ids, changes):
        for lead_id in ids:
            store.update_lead(lead_id, changes)
        self.refresh()
        self.details.reload()
        self.statusBar().showMessage(f'Updated {len(ids)} lead{"s" if len(ids) > 1 else ""}', 4000)

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
        self.statusBar().showMessage(f"{row['name']} {verb} from the browser", 8000)
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
            self.statusBar().showMessage(f'Scanning {len(ids)} website{"s" if len(ids) > 1 else ""} in the background…')

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
            rows = store.query_leads(self.search.text().strip(), self.stage_filter.currentText(), self.view.currentData() or 'All leads')
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
            self.statusBar().showMessage(f'{due} follow-up{"s" if due > 1 else ""} due — choose “Follow-ups due” in the view list.', 15000)
            self.tray.showMessage('LeadDock', f'{due} follow-up{"s" if due > 1 else ""} due today', QSystemTrayIcon.MessageIcon.Information, 4000)

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
