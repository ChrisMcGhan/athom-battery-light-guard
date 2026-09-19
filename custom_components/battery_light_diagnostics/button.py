"""Manual incident marker for normal remote use."""
from homeassistant.components.button import ButtonEntity
from . import DOMAIN
async def async_setup_platform(hass,config,async_add_entities,discovery_info=None):
    async_add_entities([ReportButton(hass.data[DOMAIN])])
class ReportButton(ButtonEntity):
    _attr_name='Battery Light Report Missed On'
    _attr_unique_id='battery_light_diagnostics_report_missed_on'
    _attr_icon='mdi:bug-outline'
    def __init__(self,recorder):self.recorder=recorder
    async def async_press(self):await self.recorder.report()
