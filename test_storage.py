import gzip,importlib.util,json,pathlib,tempfile,time,unittest
spec=importlib.util.spec_from_file_location('rf_storage',pathlib.Path(__file__).parent/'custom_components/battery_light_diagnostics/storage.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class StorageTests(unittest.TestCase):
 def test_rotation_restart_and_incident(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=m.Store(tmp,max_bytes=1800,incidents=2)
   now=time.time()
   for i in range(20):stats=store.append([{'ts':now+i/100,'kind':'raw','counter':i,'timings_us':[500,-1600]*20}])
   self.assertLessEqual(stats['payload_bytes'],1800)
   restarted=m.Store(tmp,max_bytes=1800,incidents=2)
   for _ in range(3):report=restarted.report(60,'test incident')
   files=list((pathlib.Path(tmp)/'incidents').glob('*.jsonl.gz'));self.assertEqual(len(files),2)
   with gzip.open(report['file'],'rt') as f:rows=[json.loads(line) for line in f]
   self.assertEqual(rows[-1]['counter'],19);self.assertGreater(rows[0]['records'],0)
   self.assertFalse(rows[0]['truncated']);self.assertFalse(list(pathlib.Path(tmp).rglob('*.tmp')))
 def test_age_retention(self):
  with tempfile.TemporaryDirectory() as tmp:
   store=m.Store(tmp,retention_days=1)
   store.append([{'ts':time.time()-90000,'kind':'old'}])
   stats=store.append([{'ts':time.time(),'kind':'new'}])
   self.assertEqual(stats['records'],1)
if __name__=='__main__':unittest.main()
