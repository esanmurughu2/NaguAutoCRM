import os,tempfile,unittest,json,io
from email.parser import BytesParser
from email.policy import default
os.environ['NAGU_DATA']=tempfile.mkdtemp(prefix='nagu-test-')
import app
class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):app.init()
 def request(self,path,body=None,token='',csrf=''):
  h=app.Handler.__new__(app.Handler);h.path=path;raw=json.dumps(body).encode() if body is not None else b''
  h.headers={'Host':'127.0.0.1:8765','Content-Length':str(len(raw)),'Cookie':f'nagu_session={token}','X-CSRF-Token':csrf};h.rfile=io.BytesIO(raw);result={}
  def send(status,data,kind='application/json',extra=None):result.update(status=status,data=data,kind=kind,extra=extra or {})
  h.send=send;h.handle_request('POST' if body is not None else 'GET');return result
 def test_workflow(self):
  self.assertEqual(self.request('/api/state')['status'],401)
  login=self.request('/api/login',{'email':app.USER,'password':app.PASSWORD});token=login['extra']['Set-Cookie'].split(';')[0].split('=')[1];csrf=login['data']['csrf']
  def req(path,body=None):return self.request(path,body,token,csrf)
  self.assertEqual(self.request('/api/customers',{},token,'wrong')['status'],403)
  c=req('/api/customers',{'name':'Test Customer','email':'test@example.com','notes':'PRIVATE INTERNAL NOTE'})['data']['id']
  data={'customer_id':c,'date':'2026-10-02','vehicle':'Test vehicle','notes':'Customer-facing note','tax_rate':'13','lines':[{'description':'Service','quantity':'2','price':'12.35'}]}
  iid=req('/api/invoices',data)['data']['id'];r=req(f'/api/invoices/{iid}/finalize',{'version':1});self.assertEqual(r['status'],200)
  self.assertEqual(req(f'/api/invoices/{iid}/finalize',{'version':1})['data']['number'],r['data']['number'])
  self.assertEqual(req('/api/invoices',{**data,'id':iid,'version':2})['status'],409)
  pdf=req(f'/api/invoices/{iid}/pdf');self.assertTrue(pdf['data'].startswith(b'%PDF'))
  e=req(f'/api/invoices/{iid}/email',{'recipient':'preview@example.com'});msg=BytesParser(policy=default).parsebytes(req(f'/api/emails/{e["data"]["id"]}/download')['data'])
  self.assertEqual(list(msg.iter_attachments())[0].get_payload(decode=True),pdf['data'])
  st=req('/api/state')['data'];inv=next(i for i in st['invoices'] if i['id']==iid)
  self.assertEqual(inv['total'],2791);self.assertNotIn('notes',inv['snapshot']['customer'])
  customer=next(x for x in st['customers'] if x['id']==c)
  self.assertEqual(req('/api/customers',{**customer,'name':'Changed'})['status'],200)
  self.assertEqual(req('/api/customers',{**customer,'name':'Stale'})['status'],409)
  self.assertEqual(req(f'/api/invoices/{iid}/pdf')['data'],pdf['data'])
  with app.conn() as db:self.assertEqual(db.execute('SELECT name FROM customers WHERE id=?',(c,)).fetchone()[0],'Changed')
 def test_decimal_validation(self):
  self.assertEqual(app.calculate([{'description':'fraction','quantity':'3','price':'0.10'}],'13')[1:],(30,4,34))
  for qty,price in [('0','1'),('NaN','1'),('1','-1'),('1','1.001')]:
   with self.assertRaises(ValueError):app.calculate([{'description':'x','quantity':qty,'price':price}],'13')
if __name__=='__main__':unittest.main()
