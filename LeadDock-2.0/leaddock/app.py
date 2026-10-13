"""LeadDock 2.0 — local-first prospecting CRM. Python 3.10+ / PySide6."""
import csv, json, os, re, secrets, shutil, sqlite3, sys, threading, webbrowser
from datetime import datetime, date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from PySide6.QtCore import Qt, QTimer, Signal, QObject, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QPlainTextEdit, QComboBox, QTableWidget, QTableWidgetItem,
    QSplitter, QFormLayout, QFileDialog, QMessageBox, QTabWidget, QHeaderView, QSystemTrayIcon,
    QMenu, QStyle, QFrame, QCheckBox, QDateEdit, QSpinBox, QAbstractItemView, QDialog)

APP_DIR = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'LeadDock2'
APP_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = APP_DIR / 'leads.sqlite3'
KEY_PATH = APP_DIR / 'capture_key.txt'
if not KEY_PATH.exists(): KEY_PATH.write_text(secrets.token_urlsafe(32), encoding='utf-8')
KEY = KEY_PATH.read_text(encoding='utf-8').strip()
PORT = 18765
STAGES = ['New', 'Qualified', 'Contacted', 'Follow Up', 'Proposal', 'Won', 'Lost']
FIELDS = ['name','category','phone','website','address','maps_url','email','contact_name','city','rating','review_count','status','priority','estimated_value','next_followup','notes']

def now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def clean_url(s):
    s = (s or '').strip()
    if s and not re.match(r'^https?://', s, re.I): s = 'https://' + s
    return s

def db_connect():
    cx = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    cx.row_factory = sqlite3.Row
    cx.execute('PRAGMA journal_mode=WAL')
    cx.execute('PRAGMA busy_timeout=15000')
    return cx

def init_db():
    with db_connect() as cx:
        cx.execute('''CREATE TABLE IF NOT EXISTS leads(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL DEFAULT '', category TEXT DEFAULT '',
        phone TEXT DEFAULT '', website TEXT DEFAULT '', address TEXT DEFAULT '', maps_url TEXT DEFAULT '',
        email TEXT DEFAULT '', contact_name TEXT DEFAULT '', city TEXT DEFAULT '', rating TEXT DEFAULT '',
        review_count TEXT DEFAULT '', status TEXT DEFAULT 'New', priority TEXT DEFAULT 'Normal',
        estimated_value REAL DEFAULT 0, next_followup TEXT DEFAULT '', notes TEXT DEFAULT '',
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL)''')
        cx.execute('''CREATE TABLE IF NOT EXISTS activities(id INTEGER PRIMARY KEY AUTOINCREMENT,
           lead_id INTEGER NOT NULL, action TEXT NOT NULL, detail TEXT DEFAULT '', at TEXT NOT NULL,
           FOREIGN KEY(lead_id) REFERENCES leads(id))''')
        cx.execute('CREATE INDEX IF NOT EXISTS leads_name ON leads(name)')
        cx.execute('CREATE INDEX IF NOT EXISTS leads_stage ON leads(status)')

def norm_phone(s): return re.sub(r'\D', '', s or '')[-10:]
def norm_site(s):
    try: return urlparse(clean_url(s)).netloc.lower().removeprefix('www.')
    except Exception: return ''

def store_lead(data):
    data = {k: str(data.get(k, '') or '').strip() for k in FIELDS}
    data['name'] = data['name'][:250]
    if not data['name']: raise ValueError('Business name is required.')
    data['website'] = clean_url(data['website'])
    data['maps_url'] = clean_url(data['maps_url'])
    with db_connect() as cx:
        existing = None
        if data['maps_url']:
            existing = cx.execute('SELECT id FROM leads WHERE maps_url=?',(data['maps_url'],)).fetchone()
        if not existing and data['phone'] and len(norm_phone(data['phone'])) >= 10:
            existing = cx.execute('SELECT id FROM leads WHERE name=? COLLATE NOCASE AND phone=?',(data['name'], data['phone'])).fetchone()
        if not existing and data['address']:
            existing = cx.execute('SELECT id FROM leads WHERE name=? COLLATE NOCASE AND address=? COLLATE NOCASE',(data['name'],data['address'])).fetchone()
        if not existing and not data['address'] and not data['phone']:
            existing = cx.execute('SELECT id FROM leads WHERE name=? COLLATE NOCASE AND website=?',(data['name'],data['website'])).fetchone() if data['website'] else None
        if existing:
            lead_id = existing['id']
            row = cx.execute('SELECT * FROM leads WHERE id=?',(lead_id,)).fetchone()
            updates = {k:v for k,v in data.items() if v and k not in ('status','priority','estimated_value','notes','contact_name','email','next_followup') and (not row[k] or k in ('phone','address','website','maps_url','category','rating','review_count'))}
            if updates:
                updates['updated_at'] = now()
                cx.execute('UPDATE leads SET '+ ','.join(f'{k}=?' for k in updates)+' WHERE id=?',(*updates.values(),lead_id))
            result = 'updated'
        else:
            data['status'] = data['status'] if data['status'] in STAGES else 'New'
            data['priority'] = data['priority'] if data['priority'] in ['Low','Normal','High','Urgent'] else 'Normal'
            try: data['estimated_value'] = float(data['estimated_value'] or 0)
            except ValueError: data['estimated_value'] = 0
            columns = list(data) + ['created_at','updated_at']
            values = list(data.values()) + [now(),now()]
            cursor = cx.execute('INSERT INTO leads ('+','.join(columns)+') VALUES ('+','.join('?' for _ in values)+')',values)
            lead_id = cursor.lastrowid
            result = 'created'
        cx.execute('INSERT INTO activities(lead_id,action,detail,at) VALUES(?,?,?,?)',(lead_id,'Captured' if result=='created' else 'Refreshed','Google Maps / import',now()))
        return lead_id, result

class Notify(QObject):
    captured = Signal(int, str)

class CaptureHandler(BaseHTTPRequestHandler):
    notifier = None
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-LeadDock-Key')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.end_headers()
    def respond(self, code, body):
        blob = json.dumps(body).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(blob)))
        self.send_header('Access-Control-Allow-Origin','*')
        self.end_headers(); self.wfile.write(blob)
    def do_GET(self):
        if self.path == '/health': self.respond(200,{'ok':True,'app':'LeadDock 2.0'})
        else: self.respond(404,{'error':'Not found'})
    def do_POST(self):
        if self.path != '/capture': return self.respond(404,{'error':'Not found'})
        if not secrets.compare_digest(self.headers.get('X-LeadDock-Key',''), KEY): return self.respond(403,{'error':'Invalid pairing key'})
        try:
            length = int(self.headers.get('Content-Length','0'))
            if length < 1 or length > 32768: return self.respond(413,{'error':'Payload size invalid'})
            body = json.loads(self.rfile.read(length))
            if not isinstance(body,dict): raise ValueError('Expected an object')
            if not str(body.get('maps_url','')).startswith('https://www.google.'): raise ValueError('Open a Google Maps business first')
            id_, outcome = store_lead(body)
            self.respond(200,{'ok':True,'id':id_,'result':outcome,'name':body['name']})
            self.notifier.captured.emit(id_,outcome)
        except (ValueError, KeyError, json.JSONDecodeError) as e: self.respond(400,{'error':str(e)})
        except Exception as e: self.respond(500,{'error':'Capture failed: '+str(e)})
    def log_message(self,*args): pass

STYLE = '''
QWidget { background:#0d111b; color:#e9edf7; font-family:'Segoe UI'; font-size:12px; }
QMainWindow,QDialog {background:#0d111b;} QLabel#heading{font-size:22px;font-weight:700;}
QLabel#hint{color:#93a0b8;} QFrame#panel {background:#151b2a;border:1px solid #293248;border-radius:12px;}
QLineEdit,QPlainTextEdit,QComboBox,QDateEdit,QSpinBox {background:#121929; border:1px solid #303a50; border-radius:7px;padding:7px;selection-background-color:#4364db;}
QLineEdit:focus,QPlainTextEdit:focus,QComboBox:focus{border:1px solid #6e8df9;}
QPushButton {background:#252e43; border:1px solid #35415a; border-radius:7px; padding:8px 11px;font-weight:600;}
QPushButton:hover{background:#34425e;} QPushButton#primary{background:#566ff0;border:0;color:white;} QPushButton#primary:hover{background:#7189ff;}
QTableWidget{background:#121929;alternate-background-color:#172035;gridline-color:#263249;border:1px solid #283247;border-radius:8px;}
QHeaderView::section{background:#202a3e;color:#b5c1d6;border:0;padding:9px;}
QTableWidget::item:selected{background:#34446b;color:white;}
QTabWidget::pane{border:0;} QTabBar::tab{padding:9px 15px;background:#182032;margin-right:5px;border-radius:7px;}
QTabBar::tab:selected{background:#4057b1;} QSplitter::handle{background:#253049;}
QScrollBar:vertical{background:#101624;width:10px;} QScrollBar::handle:vertical{background:#39445d;border-radius:5px;}
'''

class LeadDetails(QWidget):
    def __init__(self, changed):
        super().__init__(); self.lead_id=None; self.loading=False; self.changed=changed; self.controls={}
        lay=QVBoxLayout(self); lay.setContentsMargins(16,12,16,12); lay.setSpacing(8)
        self.title=QLabel('Select a lead'); self.title.setObjectName('heading'); lay.addWidget(self.title)
        self.subtitle=QLabel('Edit any field. Changes save automatically.'); self.subtitle.setObjectName('hint'); lay.addWidget(self.subtitle)
        links=QHBoxLayout(); lay.addLayout(links)
        self.open_map=QPushButton('↗ Maps'); self.open_web=QPushButton('↗ Website'); self.copy_phone=QPushButton('Copy phone');
        for b in (self.open_map,self.open_web,self.copy_phone): links.addWidget(b)
        self.open_map.clicked.connect(lambda: self.open_link('maps_url'))
        self.open_web.clicked.connect(lambda: self.open_link('website'))
        self.copy_phone.clicked.connect(self.copy_number)
        form_widget=QWidget(); form=QFormLayout(form_widget); form.setLabelAlignment(Qt.AlignmentFlag.AlignRight);form.setSpacing(9)
        labels={'name':'Business','category':'Category','phone':'Phone','website':'Website','address':'Address','maps_url':'Google Maps URL','email':'Email','contact_name':'Contact person','city':'City','rating':'Google rating','review_count':'Review count','status':'Pipeline stage','priority':'Priority','estimated_value':'Deal value ($)','next_followup':'Follow-up (YYYY-MM-DD)','notes':'Notes'}
        for field,label in labels.items():
            if field in ('status','priority'):
                c=QComboBox(); c.addItems(STAGES if field=='status' else ['Low','Normal','High','Urgent']); c.currentTextChanged.connect(lambda _,f=field: self.save_field(f))
            elif field=='notes':
                c=QPlainTextEdit();c.setPlaceholderText('Website opportunity, outreach notes, next steps…');c.setMinimumHeight(130)
                c.textChanged.connect(lambda f=field: self.delayed_save(f))
            else:
                c=QLineEdit(); c.setPlaceholderText(label)
                c.textEdited.connect(lambda _,f=field: self.delayed_save(f))
            self.controls[field]=c;form.addRow(label+':',c)
        from PySide6.QtWidgets import QScrollArea
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);scroll.setWidget(form_widget); lay.addWidget(scroll,1)
        footer=QHBoxLayout();lay.addLayout(footer)
        self.saved=QLabel('');self.saved.setObjectName('hint');footer.addWidget(self.saved);footer.addStretch()
        self.delete=QPushButton('Delete lead');self.delete.clicked.connect(self.delete_lead);footer.addWidget(self.delete)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.save_pending)
        self.pending=set()
    def delayed_save(self, field):
        if self.loading or self.lead_id is None: return
        self.pending.add(field);self.saved.setText('Editing…');self.timer.start(500)
    def set_row(self, row):
        if self.pending: self.save_pending()
        self.loading=True; self.lead_id=row['id'] if row else None
        self.title.setText(row['name'] if row else 'Select a lead')
        for field,control in self.controls.items():
            val=str(row[field] or '') if row else ''
            if isinstance(control,QComboBox):
                ix=control.findText(val);control.setCurrentIndex(ix if ix>=0 else 0)
            elif isinstance(control,QPlainTextEdit):control.setPlainText(val)
            else:control.setText(val)
            control.setEnabled(bool(row))
        self.saved.setText('Auto-save is on' if row else '');self.loading=False
    def value(self,field):
        c=self.controls[field]
        return c.currentText() if isinstance(c,QComboBox) else c.toPlainText() if isinstance(c,QPlainTextEdit) else c.text()
    def save_field(self,field):
        if not self.loading and self.lead_id: self.pending.add(field);self.timer.start(100)
    def save_pending(self):
        if not self.lead_id or not self.pending:return
        fs=list(self.pending);self.pending.clear()
        vals=[self.value(f) for f in fs]
        if 'name' in fs and not self.value('name').strip(): self.saved.setText('Business name cannot be blank');return
        try:
            with db_connect() as cx:
                cx.execute('UPDATE leads SET '+','.join(f'{f}=?' for f in fs)+',updated_at=? WHERE id=?',(*vals,now(),self.lead_id))
            self.saved.setText('✓ Saved');self.title.setText(self.value('name'));self.changed(self.lead_id)
        except Exception as e:self.saved.setText('Save error: '+str(e))
    def open_link(self,field):
        if self.lead_id and self.value(field):QDesktopServices.openUrl(QUrl(clean_url(self.value(field))))
    def copy_number(self):
        QApplication.clipboard().setText(self.value('phone'))
    def delete_lead(self):
        if self.lead_id and QMessageBox.question(self,'Delete lead','Permanently delete this lead?')==QMessageBox.StandardButton.Yes:
            with db_connect() as cx:
                cx.execute('DELETE FROM activities WHERE lead_id=?',(self.lead_id,))
                cx.execute('DELETE FROM leads WHERE id=?',(self.lead_id,))
            self.set_row(None);self.changed(None)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle('LeadDock 2.0 — Prospecting CRM');self.resize(1360,820);self.setMinimumSize(850,550)
        self.setStyleSheet(STYLE); self.notify=Notify();self.notify.captured.connect(self.on_capture)
        root=QWidget(); self.setCentralWidget(root); top=QVBoxLayout(root);top.setContentsMargins(16,13,16,12);top.setSpacing(10)
        header=QHBoxLayout();top.addLayout(header)
        brand=QLabel('◈  LeadDock');brand.setObjectName('heading');header.addWidget(brand)
        header.addStretch();self.count=QLabel('0 leads');self.count.setObjectName('hint');header.addWidget(self.count)
        for title,handler in [('Add lead',self.add_lead),('Import CSV',self.import_csv),('Export CSV',self.export_csv),('Backup DB',self.backup),('Connect Edge',self.pairing)]:
            b=QPushButton(title);b.clicked.connect(handler);header.addWidget(b)
            if title=='Add lead':b.setObjectName('primary')
        desc=QLabel('Your local-first sales workspace  •  Capture from Google Maps with the Edge extension  •  Changes auto-save')
        desc.setObjectName('hint');top.addWidget(desc)
        bar=QHBoxLayout();top.addLayout(bar)
        self.search=QLineEdit();self.search.setPlaceholderText('Search businesses, phone numbers, websites, cities…');self.search.textChanged.connect(self.refresh);bar.addWidget(self.search,4)
        self.filter=QComboBox();self.filter.addItems(['All stages']+STAGES);self.filter.currentTextChanged.connect(self.refresh);bar.addWidget(self.filter,1)
        self.high=QCheckBox('High priority only');self.high.stateChanged.connect(self.refresh);bar.addWidget(self.high)
        splitter=QSplitter(Qt.Orientation.Horizontal);top.addWidget(splitter,1)
        left=QWidget();l=QVBoxLayout(left);l.setContentsMargins(0,0,4,0)
        self.tabs=QTabWidget();l.addWidget(self.tabs)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['Business','Stage','Priority','Phone','Website','City','Follow-up']);self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.setAlternatingRowColors(True);self.table.verticalHeader().hide();self.table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.selected);self.tabs.addTab(self.table,'All leads')
        self.pipeline=QTableWidget(0,4);self.pipeline.setHorizontalHeaderLabels(['Stage','Leads','Potential value','Next action']);self.pipeline.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch);self.pipeline.verticalHeader().hide();self.tabs.addTab(self.pipeline,'Pipeline summary')
        splitter.addWidget(left);self.details=LeadDetails(self.on_edit);splitter.addWidget(self.details);splitter.setSizes([770,540])
        self.statusBar().showMessage('Database: '+str(DB_PATH))
        self.refresh()
        try:
            CaptureHandler.notifier=self.notify
            self.server=ThreadingHTTPServer(('127.0.0.1',PORT),CaptureHandler)
            threading.Thread(target=self.server.serve_forever,daemon=True).start()
            self.statusBar().showMessage('Capture service running at 127.0.0.1:'+str(PORT)+'  |  Database: '+str(DB_PATH))
        except OSError as e:
            QMessageBox.warning(self,'Capture service unavailable','Port 18765 is already in use. Close any other LeadDock instance.\n\n'+str(e))
        self.tray=QSystemTrayIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon),self)
        traymenu=QMenu();action=traymenu.addAction('Open LeadDock');action.triggered.connect(self.showNormal);quit_action=traymenu.addAction('Exit LeadDock');quit_action.triggered.connect(QApplication.instance().quit);self.tray.setContextMenu(traymenu);self.tray.show()
    def refresh(self,*_):
        selected=self.details.lead_id if hasattr(self,'details') else None
        q=self.search.text().strip();stage=self.filter.currentText();high=self.high.isChecked()
        where=[];args=[]
        if q:
            where.append('('+' OR '.join(f'{f} LIKE ?' for f in ['name','phone','website','city','address','category'])+')');args.extend(['%'+q+'%']*6)
        if stage!='All stages':where.append('status=?');args.append(stage)
        if high:where.append("priority IN ('High','Urgent')")
        with db_connect() as cx:
            rows=cx.execute('SELECT * FROM leads'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY updated_at DESC',args).fetchall()
            stages=cx.execute('SELECT status,COUNT(*) n,COALESCE(SUM(estimated_value),0) value FROM leads GROUP BY status').fetchall()
            total=cx.execute('SELECT count(*) FROM leads').fetchone()[0]
        self.count.setText(f'{total} leads · {len(rows)} shown')
        self.table.blockSignals(True);self.table.setRowCount(len(rows))
        self.row_ids=[];selrow=None
        for i,r in enumerate(rows):
            self.row_ids.append(r['id']);vals=[r['name'],r['status'],r['priority'],r['phone'],r['website'],r['city'],r['next_followup']]
            for j,v in enumerate(vals):self.table.setItem(i,j,QTableWidgetItem(str(v or '')))
            if r['id']==selected:selrow=i
        self.table.blockSignals(False)
        if selrow is not None:self.table.selectRow(selrow)
        self.pipeline.setRowCount(len(STAGES));summary={r['status']:r for r in stages}
        for i,s in enumerate(STAGES):
            r=summary.get(s);vals=[s,str(r['n'] if r else 0),'${:,.0f}'.format(r['value'] if r else 0),'Open lead list and filter by stage']
            for j,v in enumerate(vals):self.pipeline.setItem(i,j,QTableWidgetItem(v))
    def selected(self):
        items=self.table.selectedItems()
        if not items:return
        row=self.table.currentRow()
        if row<0 or row>=len(self.row_ids):return
        with db_connect() as cx:r=cx.execute('SELECT * FROM leads WHERE id=?',(self.row_ids[row],)).fetchone()
        self.details.set_row(r)
    def select_id(self,id_):
        self.search.clear();self.filter.setCurrentIndex(0);self.high.setChecked(False);self.refresh()
        if id_ in self.row_ids:self.table.selectRow(self.row_ids.index(id_));self.selected()
    def on_edit(self,id_):self.refresh()
    def on_capture(self,id_,outcome):
        self.select_id(id_);self.showNormal();self.raise_();self.activateWindow()
        self.statusBar().showMessage('Lead '+outcome+' successfully',7000)
        if self.tray.isVisible():self.tray.showMessage('LeadDock', 'Business '+outcome, QSystemTrayIcon.MessageIcon.Information,2000)
    def add_lead(self):
        try:id_,_=store_lead({'name':'New business '+datetime.now().strftime('%H:%M:%S')})
        except Exception as e:QMessageBox.warning(self,'Unable to add',str(e));return
        self.select_id(id_);self.details.controls['name'].setFocus();self.details.controls['name'].selectAll()
    def export_csv(self):
        target,_=QFileDialog.getSaveFileName(self,'Export leads',str(Path.home()/'leaddock_leads.csv'),'CSV files (*.csv)')
        if not target:return
        with db_connect() as cx: rows=cx.execute('SELECT * FROM leads ORDER BY name').fetchall()
        with open(target,'w',encoding='utf-8-sig',newline='') as f:
            writer=csv.writer(f);cols=['id']+FIELDS+['created_at','updated_at'];writer.writerow(cols)
            for r in rows:writer.writerow([r[c] for c in cols])
        QMessageBox.information(self,'Export complete',f'Exported {len(rows)} leads.')
    def import_csv(self):
        source,_=QFileDialog.getOpenFileName(self,'Import leads','','CSV files (*.csv)')
        if not source:return
        n=0;errors=0
        with open(source,'r',encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                try:store_lead(r);n+=1
                except Exception:errors+=1
        self.refresh();QMessageBox.information(self,'Import complete',f'Processed: {n} rows\nSkipped: {errors} rows')
    def backup(self):
        target,_=QFileDialog.getSaveFileName(self,'Backup database',str(Path.home()/('LeadDock_backup_'+date.today().isoformat()+'.sqlite3')),'SQLite Database (*.sqlite3)')
        if target:
            with db_connect() as src, sqlite3.connect(target) as dest:src.backup(dest)
            QMessageBox.information(self,'Backup created','Saved database backup to:\n'+target)
    def pairing(self):
        d=QDialog(self);d.setWindowTitle('Connect Edge extension');d.setMinimumWidth(560);d.setStyleSheet(STYLE);layout=QVBoxLayout(d)
        info=QLabel('1. In Edge, open edge://extensions and enable Developer mode.\n2. Click “Load unpacked”, and choose LeadDock-2.0\\extension.\n3. Click the LeadDock extension and paste this pairing key.\n4. Open a Google Maps business profile, then click “Capture business”.')
        info.setWordWrap(True);layout.addWidget(info)
        field=QLineEdit(KEY);field.setReadOnly(True);layout.addWidget(field)
        b=QPushButton('Copy pairing key');b.clicked.connect(lambda:QApplication.clipboard().setText(KEY));layout.addWidget(b)
        msg=QLabel('Your key stays on your computer. Don’t share it publicly.');msg.setObjectName('hint');layout.addWidget(msg)
        d.exec()
    def closeEvent(self,event):
        if self.details.pending:self.details.save_pending()
        # Keep running in tray. Use tray > Exit to fully stop.
        self.hide();event.ignore()

def main():
    init_db();app=QApplication(sys.argv);app.setApplicationName('LeadDock');app.setQuitOnLastWindowClosed(False)
    window=MainWindow();window.show();sys.exit(app.exec())
if __name__=='__main__':main()
