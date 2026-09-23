import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import automation, pins
from esphome.const import CONF_ID, CONF_PIN

DEPENDENCIES = ["esp32"]
ns = cg.esphome_ns.namespace("battery_light_stream")
StreamReceiver = ns.class_("StreamReceiver", cg.Component)
CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(StreamReceiver),
    cv.Required(CONF_PIN): pins.internal_gpio_input_pin_schema,
    cv.Optional("on_code"): automation.validate_automation(single=True),
}).extend(cv.COMPONENT_SCHEMA)

async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_pin(await cg.gpio_pin_expression(config[CONF_PIN])))
    if "on_code" in config:
        await automation.build_automation(var.get_trigger(), [(cg.uint32, "code")], config["on_code"])
