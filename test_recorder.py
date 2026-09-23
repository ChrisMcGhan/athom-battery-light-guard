"""Exercise real receiver callbacks with synthetic inputs; no network or HA actions."""
import asyncio,importlib.util,json,pathlib,sys,tempfile,types
from unittest.mock import AsyncMock
root=pathlib.Path(__file__).resolve().parent
for name in ['homeassistant','homeassistant.const','homeassistant.helpers','homeassistant.helpers.config_validation','homeassistant.helpers.discovery','homeassistant.core']:
    sys.modules[name]=types.ModuleType(name)
sys.modules['homeassistant.const'].EVENT_HOMEASSISTANT_STOP='stop'
cv=sys.modules['homeassistant.helpers.config_validation'];cv.string=str;cv.slug=str
sys.modules['homeassistant.core'].SupportsResponse=types.SimpleNamespace(OPTIONAL=1)
component=root/'custom_components/battery_light_diagnostics'
spec=importlib.util.spec_from_file_location('recorder',component/'__init__.py',submodule_search_locations=[str(component)]);mod=importlib.util.module_from_spec(spec);sys.modules['recorder']=mod;spec.loader.exec_module(mod)
class Client:
    clients=[]
    def __init__(self,host,*a,**kw):self.host=host;self.__class__.clients.append(self)
    async def connect(self,**kw):pass
    async def disconnect(self):pass
    async def device_info(self):return types.SimpleNamespace(mac_address=self.host,project_version='battery-guard-1.6',compilation_time='test')
    async def list_entities_services(self):
        cls=type('RadioFrequencyInfo',(),{})
        rx=cls();rx.key=1;rx.name='RF';rx.capabilities=2
        tx=cls();tx.key=2;tx.name='TX';tx.capabilities=1
        return [rx,tx],[]
    def subscribe_infrared_rf_receive(self,callback):self.receive=callback
    def subscribe_logs(self,callback,**kw):self.log=callback
    def subscribe_states(self,*a,**kw):pass
mod.APIClient=Client
async def main():
    with tempfile.TemporaryDirectory() as temp:
        events=[]
        hass=types.SimpleNamespace(config=types.SimpleNamespace(path=lambda x:temp),states=types.SimpleNamespace(async_set=lambda *a:None),bus=types.SimpleNamespace(async_fire=lambda *a:events.append(a)),async_add_executor_job=AsyncMock(side_effect=lambda f,*a:f(*a)))
        recorder=mod.Recorder(hass,{'receivers':[{'id':r,'host':r,'expected_mac':r} for r in ['study','bedroom','living_room']]})
        recorder.tasks=[asyncio.create_task(recorder.connection_loop(r)) for r in recorder.receivers]
        for _ in range(10):await asyncio.sleep(0)
        frame=json.loads((root/'samples/frames.json').read_text())['Power On']['timings_us']
        for client in Client.clients:
            client.receive(types.SimpleNamespace(key=2,timings=frame)) # transmitter must be ignored
            client.receive(types.SimpleNamespace(key=1,timings=frame))
        assert len(events)==3,events
        assert len({e[1]['correlation_id'] for e in events})==1
        assert {e[1]['receiver_id'] for e in events}=={'study','bedroom','living_room'}
        for client in Client.clients:
            client.log(types.SimpleNamespace(message=b'\x1b[0;32m[I][battery_guard:123]: BGSTREAM code=E0960107\x1b[0m'))
            client.log(types.SimpleNamespace(message=b'[I][battery_guard_diag:123]: BGSTREAM code=E0960107'))
        assert len(events)==4,events  # Only verified Study firmware's live marker.
        assert events[-1][1]['source']=='gpio_stream'
        assert len({e[1]['correlation_id'] for e in events})==1
        await recorder.flush()
        import sqlite3
        with sqlite3.connect(pathlib.Path(temp)/'rolling.sqlite3') as db:
            rows=[json.loads(x[0]) for x in db.execute("select payload from records where kind='recognized'")]
            assert len(rows)==4
            assert all(r['capture_id'] and r['receiver_mac'] for r in rows)
        await recorder.stop(None)
        assert not recorder.connected
        print('Three receiver callbacks, TX exclusion, correlation, durable records and clean shutdown passed.')
asyncio.run(main())
