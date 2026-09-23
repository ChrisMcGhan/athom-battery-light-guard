"""Persist a private RF diagnostic stream independently of the guard's control loop."""
import asyncio
import contextlib
from datetime import datetime,timezone
import logging
import time
import uuid
import voluptuous as vol
from aioesphomeapi import APIClient, LogLevel
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.core import SupportsResponse
from .storage import Store
from .decoder import decode, NAMES, Correlator, stream_code

DOMAIN='battery_light_diagnostics'
LOGGER=logging.getLogger(__name__)
RECEIVER_SCHEMA=vol.Schema({vol.Required('id'):cv.slug,vol.Required('host'):cv.string,vol.Required('expected_mac'):cv.string,vol.Optional('password',default=''):cv.string,vol.Optional('noise_psk'):cv.string})
CONFIG_SCHEMA=vol.Schema({DOMAIN:vol.Schema({vol.Optional('host'):cv.string,vol.Optional('expected_mac'):cv.string,vol.Optional('password',default=''):cv.string,vol.Optional('noise_psk'):cv.string,vol.Optional('receivers'):[RECEIVER_SCHEMA]})},extra=vol.ALLOW_EXTRA)

def iso(value):
    return datetime.fromtimestamp(value,timezone.utc).isoformat() if value else None

class Recorder:
    def __init__(self,hass,config):
        self.hass=hass;self.config=config;self.store=Store(hass.config.path('battery_light_diagnostics'))
        self.queue=asyncio.Queue(maxsize=512);self.dropped=0;self.connected=False
        self.closing=False;self.last_error=None
        self.stats={};self.last_incident=None;self.raw_count=0
        self.lock=asyncio.Lock();self.tasks=[]
        self.receivers=config.get('receivers') or [dict(config,id='study')]
        if len({r['id'] for r in self.receivers})!=len(self.receivers):raise ValueError('Duplicate receiver ID')
        if len({r['expected_mac'].lower() for r in self.receivers})!=len(self.receivers):raise ValueError('Duplicate receiver MAC')
        self.connections={};self.receiver_status={r['id']:{'connected':False,'raw_count':0} for r in self.receivers}
        self.correlator=Correlator()

    def record(self,kind,**payload):
        item={'ts':time.time(),'kind':kind,**payload}
        try:self.queue.put_nowait(item)
        except asyncio.QueueFull:self.dropped+=1

    def publish(self):
        state='error' if self.last_error else ('recording' if all(s['connected'] for s in self.receiver_status.values()) else ('degraded' if self.connected else 'disconnected'))
        self.hass.states.async_set('sensor.battery_light_rf_recorder',state,{
            'friendly_name':'Battery Light RF Recorder','raw_bursts_received':self.raw_count,
            'receivers':{k:dict(v) for k,v in self.receiver_status.items()},'queued':self.queue.qsize(),'dropped_records':self.dropped,'last_error':self.last_error,
            'oldest_record':iso(self.stats.get('oldest')),'newest_record':iso(self.stats.get('newest')),
            'stored_records':self.stats.get('records',0),'stored_payload_bytes':self.stats.get('payload_bytes',0),
            'last_incident':self.last_incident,'storage_directory':str(self.store.path),
            'retention':'Up to 7 days or 256 MiB payload, whichever is reached first'})

    async def flush(self):
        async with self.lock:
            batch=[]
            for _ in range(512):
                try:batch.append(self.queue.get_nowait())
                except asyncio.QueueEmpty:break
            if batch:
                try:
                    self.stats=await self.hass.async_add_executor_job(self.store.append,batch)
                    self.last_error=None
                except Exception as err:
                    self.dropped+=len(batch);self.last_error=str(err)
                    LOGGER.exception('RF diagnostic storage failed')
            self.publish()

    async def writer(self):
        while not self.closing:
            await self.flush();await asyncio.sleep(2)

    async def snapshot(self,receiver_id=None):
        for rid,(client,services) in list(self.connections.items()):
            if receiver_id is not None and rid!=receiver_id:continue
            service=next((s for s in services if s.name=='diagnostic_snapshot'),None)
            if service:
                with contextlib.suppress(Exception):await client.execute_service(service,{})

    async def report(self,minutes=60,note='Owner reported missed Power On'):
        self.record('miss_report',note=note,lookback_minutes=minutes)
        with contextlib.suppress(Exception):await self.snapshot()
        await asyncio.sleep(4)  # Let the bounded RAM dump arrive before freezing evidence.
        await self.flush()
        async with self.lock:
            result=await self.hass.async_add_executor_job(self.store.report,minutes,note)
        self.last_incident=result;self.publish();return result

    async def connection_loop(self,receiver):
        rid=receiver['id'];status=self.receiver_status[rid]
        def record(kind,**payload):self.record(kind,receiver_id=rid,receiver_mac=receiver['expected_mac'],**payload)
        while not self.closing:
            stopped=asyncio.Event()
            async def on_stop(expected):
                stopped.set()
            client=APIClient(receiver['host'],6053,receiver.get('password',''),noise_psk=receiver.get('noise_psk'),client_info='Battery Light RF Recorder')
            try:
                await asyncio.wait_for(client.connect(on_stop=on_stop,login=True),20)
                info=await client.device_info()
                if info.mac_address.lower()!=receiver['expected_mac'].lower():raise ValueError('Receiver MAC does not match configured device')
                entities,services=await client.list_entities_services();names={e.key:e.name for e in entities}
                rf_keys={e.key for e in entities if e.__class__.__name__=='RadioFrequencyInfo' and int(e.capabilities)&2}
                if not rf_keys:raise ValueError('No native radio-frequency entity found')
                def receive(message):
                    if message.key in rf_keys:
                        self.raw_count+=1;status['raw_count']+=1
                        timings=list(message.timings);capture_id=uuid.uuid4().hex
                        record('raw',capture_id=capture_id,key=message.key,timings_us=timings)
                        for offset,code in decode(timings):
                            payload={'receiver_id':rid,'receiver_mac':receiver['expected_mac'],'capture_id':capture_id,'offset':offset,'signature':f'{code:08x}','command':NAMES[code],'correlation_id':self.correlator.observe(code,time.monotonic())}
                            self.record('recognized',**payload)
                            self.hass.bus.async_fire('battery_light_rf_recognized',payload)
                def log(message):
                    text=message.message.decode(errors='replace')
                    record('device_log',message=text)
                    code=stream_code(text) if rid=='study' and info.project_version.startswith('battery-guard-') else None
                    if code is not None:
                        payload={'receiver_id':rid,'receiver_mac':receiver['expected_mac'],'capture_id':uuid.uuid4().hex,'source':'gpio_stream','signature':f'{code:08x}','command':NAMES[code],'correlation_id':self.correlator.observe(code,time.monotonic())}
                        self.record('recognized',**payload)
                        self.hass.bus.async_fire('battery_light_rf_recognized',payload)
                def state(message):
                    name=names.get(message.key,'')
                    if 'Battery Light' in name or name in ('Heap Free','Reset Reason','Uptime Sensor'):
                        value=str(getattr(message,'state',''))
                        if latest.get(name)!=value:
                            latest[name]=value;record('state',name=name,state=value)
                status['connected']=True;status['error']=None;self.connected=True;latest={}
                self.connections[rid]=(client,services)
                record('connected',firmware=info.project_version,compilation=info.compilation_time)
                client.subscribe_infrared_rf_receive(receive)
                client.subscribe_logs(log,log_level=LogLevel.LOG_LEVEL_INFO)
                client.subscribe_states(state)
                await self.snapshot(rid)
                self.publish()
                # Dump retained candidate frames once per minute, including rejection reasons.
                while not stopped.is_set() and not self.closing:
                    try:await asyncio.wait_for(stopped.wait(),60)
                    except TimeoutError:await self.snapshot(rid)
            except asyncio.CancelledError:raise
            except Exception as err:
                status['error']=str(err);record('connection_error',error=str(err));LOGGER.warning('RF recorder connection: %s',err)
            finally:
                status['connected']=False;self.connections.pop(rid,None)
                self.connected=any(s['connected'] for s in self.receiver_status.values())
                with contextlib.suppress(Exception):await client.disconnect()
                record('disconnected');self.publish()
            if not self.closing:await asyncio.sleep(15)

    async def stop(self,event):
        self.closing=True
        for task in self.tasks:task.cancel()
        await asyncio.gather(*self.tasks,return_exceptions=True)
        await self.flush()

async def async_setup(hass,config):
    if DOMAIN not in config:return True
    recorder=Recorder(hass,config[DOMAIN]);hass.data[DOMAIN]=recorder
    async def report(call):
        return await recorder.report(call.data.get('lookback_minutes',60),call.data.get('note','Owner reported missed Power On'))
    hass.services.async_register(DOMAIN,'report_missed_on',report,schema=vol.Schema({vol.Optional('lookback_minutes',default=60):vol.All(vol.Coerce(int),vol.Range(min=1,max=1440)),vol.Optional('note',default='Owner reported missed Power On'):vol.All(cv.string,vol.Length(max=500))}),supports_response=SupportsResponse.OPTIONAL)
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP,recorder.stop)
    recorder.tasks=[hass.async_create_background_task(recorder.writer(),'battery-light-rf-writer')]+[hass.async_create_background_task(recorder.connection_loop(r),'battery-light-rf-'+r['id']) for r in recorder.receivers]
    await discovery.async_load_platform(hass,'button',DOMAIN,{},config)
    return True
