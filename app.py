import os, json, sqlite3, secrets, hashlib, hmac, io, re
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs
from email.message import EmailMessage
from xml.sax.saxutils import escape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter

ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('NAGU_DATA',str(ROOT/'data'))); DATA.mkdir(exist_ok=True)
DB=DATA/'nagu.sqlite3'; SESSIONS={}
USER='demo@naguauto.local'; PASSWORD=os.environ.get('NAGU_PASSWORD','NaguDemo2026!')
SALT=b'nagu-local-prototype'; PASSHASH=hashlib.pbkdf2_hmac('sha256',PASSWORD.encode(),SALT,200000)
def now(): return datetime.now(timezone.utc).isoformat()
def conn():
 c=sqlite3.connect(DB,timeout=15); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def init():
 with conn() as c:
  c.executescript('''CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY,name TEXT NOT NULL,company TEXT DEFAULT '',phone TEXT DEFAULT '',email TEXT DEFAULT '',address TEXT DEFAULT '',notes TEXT DEFAULT '',version INTEGER DEFAULT 1,created TEXT);
CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY,customer_id INTEGER REFERENCES customers(id),date TEXT,status TEXT DEFAULT 'Draft',number TEXT UNIQUE,vehicle TEXT,notes TEXT,lines TEXT,tax_rate TEXT,subtotal INTEGER,tax INTEGER,total INTEGER,snapshot TEXT,pdf BLOB,version INTEGER DEFAULT 1,created TEXT);
CREATE TABLE IF NOT EXISTS emails(id INTEGER PRIMARY KEY,invoice_id INTEGER REFERENCES invoices(id),recipient TEXT,status TEXT,created TEXT,message BLOB);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,action TEXT,entity TEXT,created TEXT);
CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1),value TEXT);
CREATE TABLE IF NOT EXISTS sequence(id INTEGER PRIMARY KEY CHECK(id=1),next INTEGER);
INSERT OR IGNORE INTO sequence VALUES(1,1001);''')
  if not c.execute('SELECT 1 FROM settings').fetchone():
   c.execute('INSERT INTO settings VALUES(1,?)',(json.dumps({'name':'Nagu Auto','address':'Your business address · configure in Settings','phone':'','email':'invoices@example.com','tax_rate':'13','footer':'Thank you for choosing Nagu Auto.','currency':'CAD'}),))
  if not c.execute('SELECT 1 FROM customers').fetchone():
   for x in [('Alex Morgan','', '416-555-0101','alex@example.com','12 Sample Avenue, Toronto','Prefers email invoices.'),('Priya Patel','', '416-555-0102','priya@example.com','28 Example Street, Toronto',''),('Jordan Lee','Lakeview Delivery','416-555-0103','jordan@example.com','80 Demo Road, Toronto','Fleet contact. Sample data only.')]:
    c.execute('INSERT INTO customers(name,company,phone,email,address,notes,created) VALUES(?,?,?,?,?,?,?)',(*x,now()))
   lines,sub,tax,total=calculate([{'description':'Oil and filter service','quantity':'1','price':'89.95'},{'description':'Brake inspection','quantity':'1','price':'45.00'}],'13')
   c.execute('INSERT INTO invoices(customer_id,date,vehicle,notes,lines,tax_rate,subtotal,tax,total,created) VALUES(?,?,?,?,?,?,?,?,?,?)',(1,datetime.now().date().isoformat(),'2020 Toyota Corolla · DEMO VIN','',json.dumps(lines),'13',sub,tax,total,now()))
def audit(c,action,entity): c.execute('INSERT INTO audit(action,entity,created) VALUES(?,?,?)',(action,entity,now()))
def money(n): return f'{n/100:,.2f}'
def calculate(lines,rate):
 if not isinstance(lines,list) or not 1<=len(lines)<=100: raise ValueError('Add between 1 and 100 invoice lines.')
 rate=Decimal(str(rate))
 if not rate.is_finite() or not 0<=rate<=100: raise ValueError('Tax rate must be between 0 and 100.')
 result=[]; subtotal=0
 for line in lines:
  desc=str(line.get('description','')).strip(); qty=Decimal(str(line.get('quantity','0'))); price=Decimal(str(line.get('price','0')))
  if not desc or len(desc)>2000: raise ValueError('Every line needs a description (maximum 2,000 characters).')
  if not qty.is_finite() or not price.is_finite() or not 0<qty<=100000 or not 0<=price<=1000000: raise ValueError('Enter a positive quantity and a valid non-negative price.')
  if qty.as_tuple().exponent < -4 or price.as_tuple().exponent < -2: raise ValueError('Use up to 4 quantity decimals and 2 price decimals.')
  amount=int((qty*price*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP));subtotal+=amount
  result.append({'description':desc,'quantity':str(qty),'price':str(price),'amount':amount})
 tax=int((Decimal(subtotal)*rate/100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
 return result,subtotal,tax,subtotal+tax

def render_pdf(inv,customer,business):
 buf=io.BytesIO();doc=SimpleDocTemplate(buf,pagesize=letter,rightMargin=42,leftMargin=42,topMargin=42,bottomMargin=48)
 styles=getSampleStyleSheet();story=[]
 def p(t,style='Normal'): return Paragraph(escape(str(t)).replace('\n','<br/>'),styles[style])
 story += [p(business['name'],'Title'),p(business['address']),p(business['phone']),Spacer(1,22),p('INVOICE '+inv['number'],'Heading1'),p('Date: '+inv['date']),p('Currency: '+business['currency']),Spacer(1,16),p('BILL TO','Heading3'),p(customer['name']),p(customer['company']),p(customer['address']),p(customer['email']),Spacer(1,12),p('Vehicle: '+inv['vehicle']),Spacer(1,18)]
 rows=[[p('Description'),p('Qty'),p('Unit price'),p('Amount')]]
 for l in inv['lines']: rows.append([p(l['description']),p(l['quantity']),p(l['price']),p(money(l['amount']))])
 table=Table(rows,colWidths=[294,48,72,72],repeatRows=1,hAlign='LEFT')
 table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9f3f0')),('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),10),('LINEBELOW',(0,0),(-1,-1),.4,colors.HexColor('#dddddd'))]))
 story += [table,Spacer(1,20),p('Subtotal: $'+money(inv['subtotal'])),p('Tax ('+inv['tax_rate']+'%): $'+money(inv['tax'])),p('Total: $'+money(inv['total'])+' '+business['currency'],'Heading2'),Spacer(1,18),p(inv['notes']),Spacer(1,20),p(business['footer'])]
 def footer(canvas,doc):
  canvas.setFont('Helvetica',8);canvas.drawString(42,25,'LOCAL PROTOTYPE · SAMPLE / TEST INVOICE');canvas.drawRightString(570,25,f'Page {doc.page}')
 doc.build(story,onFirstPage=footer,onLaterPages=footer);return buf.getvalue()

def invoice_dict(row):
 d=dict(row);d.pop('pdf',None);d['lines']=json.loads(d['lines']);d['snapshot']=json.loads(d['snapshot']) if d['snapshot'] else None;return d
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args): pass
 def send(self,status,data,kind='application/json',extra=None):
  if kind=='application/json': data=json.dumps(data).encode()
  if isinstance(data,str): data=data.encode()
  self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','SAMEORIGIN')
  for k,v in (extra or {}).items(): self.send_header(k,v)
  self.end_headers();self.wfile.write(data)
 def do_GET(self): self.handle_request('GET')
 def do_POST(self): self.handle_request('POST')
 def handle_request(self,method):
  try: self.route(method)
  except (ValueError,InvalidOperation) as e: self.send(400,{'error':str(e) or 'Invalid numeric value.'})
  except Exception as e:
   print('Request failed:',type(e).__name__,str(e));self.send(500,{'error':'The request could not be completed. Your saved data is retained.'})
 def route(self,method):
  url=urlparse(self.path);path=url.path
  if self.headers.get('Host','').split(':')[0] not in ('127.0.0.1','localhost'):return self.send(403,{'error':'Local access only.'})
  if method=='GET' and path in ('/','/app.js','/style.css'):
   file=ROOT/'static'/({'/':'index.html','/app.js':'app.js','/style.css':'style.css'}[path]);return self.send(200,file.read_bytes(),{'/':'text/html; charset=utf-8','/app.js':'text/javascript; charset=utf-8','/style.css':'text/css; charset=utf-8'}[path])
  body={}
  if method=='POST':
   if self.headers.get('Origin') not in (None,'http://'+self.headers.get('Host','')):return self.send(403,{'error':'Invalid request origin.'})
   size=int(self.headers.get('Content-Length','0'))
   if size>300000: raise ValueError('Request too large.')
   body=json.loads(self.rfile.read(size) or '{}')
  if path=='/api/login' and method=='POST':
   if body.get('email')!=USER or not hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',str(body.get('password','')).encode(),SALT,200000),PASSHASH):return self.send(401,{'error':'Incorrect email or password.'})
   token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32);SESSIONS[token]=(csrf,datetime.now().timestamp());return self.send(200,{'csrf':csrf},extra={'Set-Cookie':f'nagu_session={token}; HttpOnly; SameSite=Strict; Path=/'})
  cookie=SimpleCookie(self.headers.get('Cookie',''));token=cookie['nagu_session'].value if 'nagu_session' in cookie else '';session=SESSIONS.get(token)
  if not session or datetime.now().timestamp()-session[1]>28800:return self.send(401,{'error':'Please sign in.'})
  if method=='POST' and self.headers.get('X-CSRF-Token')!=session[0]:return self.send(403,{'error':'Please refresh and sign in again.'})
  if path=='/api/logout' and method=='POST':
   SESSIONS.pop(token,None);return self.send(200,{'ok':True},extra={'Set-Cookie':'nagu_session=; Max-Age=0; Path=/'})
  with conn() as c:
   if path=='/api/state' and method=='GET':
    return self.send(200,{'csrf':session[0],'customers':[dict(r) for r in c.execute('SELECT * FROM customers ORDER BY name')],'invoices':[invoice_dict(r) for r in c.execute('SELECT * FROM invoices ORDER BY id DESC')],'emails':[dict(r) for r in c.execute('SELECT id,invoice_id,recipient,status,created FROM emails ORDER BY id DESC')],'audit':[dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 40')],'settings':json.loads(c.execute('SELECT value FROM settings').fetchone()[0])})
   if path=='/api/customers' and method=='POST':
    fields=[str(body.get(x,'')).strip() for x in ('name','company','phone','email','address','notes')]
    if not fields[0]:raise ValueError('Customer name is required.')
    if any(len(x)>10000 for x in fields):raise ValueError('Customer field too long.')
    if fields[3] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',fields[3]):raise ValueError('Enter a valid email or leave it blank.')
    if body.get('id'):
     r=c.execute('UPDATE customers SET name=?,company=?,phone=?,email=?,address=?,notes=?,version=version+1 WHERE id=? AND version=?',(*fields,body['id'],body['version']))
     if not r.rowcount:return self.send(409,{'error':'Customer changed elsewhere. Reload before editing.'})
     cid=body['id']
    else:cid=c.execute('INSERT INTO customers(name,company,phone,email,address,notes,created) VALUES(?,?,?,?,?,?,?)',(*fields,now())).lastrowid
    audit(c,'Customer saved',str(cid));return self.send(200,{'id':cid})
   if path=='/api/settings' and method=='POST':
    b={k:str(body.get(k,'')).strip() for k in ('name','address','phone','email','tax_rate','footer','currency')}
    if not b['name'] or b['currency']!='CAD':raise ValueError('Business name required. This prototype uses CAD.')
    calculate([{'description':'test','quantity':'1','price':'1'}],b['tax_rate']);c.execute('UPDATE settings SET value=? WHERE id=1',(json.dumps(b),));audit(c,'Settings saved','business');return self.send(200,{'ok':True})
   if path=='/api/invoices' and method=='POST':
    customer=c.execute('SELECT * FROM customers WHERE id=?',(body.get('customer_id'),)).fetchone()
    if not customer:raise ValueError('Select a customer.')
    datetime.strptime(body['date'],'%Y-%m-%d')
    lines,sub,tax,total=calculate(body['lines'],body['tax_rate']);vals=(body['customer_id'],body['date'],str(body.get('vehicle','')),str(body.get('notes','')),json.dumps(lines),str(body['tax_rate']),sub,tax,total)
    if body.get('id'):
     r=c.execute("UPDATE invoices SET customer_id=?,date=?,vehicle=?,notes=?,lines=?,tax_rate=?,subtotal=?,tax=?,total=?,version=version+1 WHERE id=? AND version=? AND status='Draft'",(*vals,body['id'],body['version']))
     if not r.rowcount:return self.send(409,{'error':'Invoice is finalized or changed elsewhere. Reload it.'})
     iid=body['id']
    else:iid=c.execute('INSERT INTO invoices(customer_id,date,vehicle,notes,lines,tax_rate,subtotal,tax,total,created) VALUES(?,?,?,?,?,?,?,?,?,?)',(*vals,now())).lastrowid
    audit(c,'Draft saved',str(iid));return self.send(200,{'id':iid})
   m=re.fullmatch(r'/api/invoices/(\d+)/(finalize|pdf|email)',path)
   if m:
    iid=int(m[1]);action=m[2]
    if method=='POST':c.execute('BEGIN IMMEDIATE')
    row=c.execute('SELECT * FROM invoices WHERE id=?',(iid,)).fetchone()
    if not row:return self.send(404,{'error':'Invoice not found.'})
    inv=invoice_dict(row)
    if action=='finalize' and method=='POST':
     if inv['status']=='Finalized':return self.send(200,{'id':iid,'number':inv['number']})
     if body.get('version')!=inv['version']:return self.send(409,{'error':'Invoice changed. Reload before finalizing.'})
     customer=dict(c.execute('SELECT * FROM customers WHERE id=?',(inv['customer_id'],)).fetchone());business=json.loads(c.execute('SELECT value FROM settings').fetchone()[0]);number=c.execute('SELECT next FROM sequence').fetchone()[0]
     inv['number']=f'NA-{number}';pdf=render_pdf(inv,customer,business)
     snapshot={'customer':{k:customer[k] for k in ('name','company','address','phone','email')},'business':business}
     c.execute("UPDATE invoices SET status='Finalized',number=?,snapshot=?,pdf=?,version=version+1 WHERE id=?",(inv['number'],json.dumps(snapshot),pdf,iid));c.execute('UPDATE sequence SET next=next+1');audit(c,'Invoice finalized',inv['number']);return self.send(200,{'id':iid,'number':inv['number']})
    if inv['status']!='Finalized':raise ValueError('Finalize the invoice first.')
    if action=='pdf' and method=='GET':return self.send(200,row['pdf'],'application/pdf',{'Content-Disposition':f'inline; filename="{inv["number"]}.pdf"'})
    if action=='email' and method=='POST':
     recipient=str(body.get('recipient','')).strip()
     if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',recipient):raise ValueError('Enter a valid recipient email.')
     msg=EmailMessage();msg['To']=recipient;msg['From']='prototype@naguauto.local';msg['Subject']='Invoice '+inv['number'];msg.set_content('Please find your invoice attached.\n\nLOCAL PROTOTYPE — this message has not been sent.');msg.add_attachment(bytes(row['pdf']),maintype='application',subtype='pdf',filename=inv['number']+'.pdf')
     eid=c.execute('INSERT INTO emails(invoice_id,recipient,status,created,message) VALUES(?,?,?,?,?)',(iid,recipient,'Preview — not sent',now(),msg.as_bytes())).lastrowid;audit(c,'Email preview created',inv['number']);return self.send(200,{'id':eid})
   m=re.fullmatch(r'/api/emails/(\d+)/download',path)
   if m and method=='GET':
    row=c.execute('SELECT message FROM emails WHERE id=?',(int(m[1]),)).fetchone()
    if row:return self.send(200,row[0],'message/rfc822',{'Content-Disposition':f'attachment; filename="invoice-email-{m[1]}.eml"'})
   return self.send(404,{'error':'Not found.'})
if __name__=='__main__':
 init();port=int(os.environ.get('PORT','8765'));print(f'NaguAuto CRM: http://127.0.0.1:{port}\nLogin: {USER}\nLocal demo password: {PASSWORD}',flush=True);ThreadingHTTPServer(('127.0.0.1',port),Handler).serve_forever()
