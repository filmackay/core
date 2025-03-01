"""Support for the sensors in a GreenEye Monitor."""
from __future__ import annotations

from typing import Any, Union

import greeneye

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import (
    CONF_NAME,
    CONF_SENSORS,
    CONF_TEMPERATURE_UNIT,
    ELECTRIC_POTENTIAL_VOLT,
    POWER_WATT,
    TIME_HOURS,
    TIME_MINUTES,
    TIME_SECONDS,
)
from homeassistant.core import Config, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import (
    CONF_CHANNELS,
    CONF_COUNTED_QUANTITY,
    CONF_COUNTED_QUANTITY_PER_PULSE,
    CONF_MONITORS,
    CONF_NET_METERING,
    CONF_NUMBER,
    CONF_PULSE_COUNTERS,
    CONF_SERIAL_NUMBER,
    CONF_TEMPERATURE_SENSORS,
    CONF_TIME_UNIT,
    CONF_VOLTAGE_SENSORS,
    DATA_GREENEYE_MONITOR,
)

DATA_PULSES = "pulses"
DATA_WATT_SECONDS = "watt_seconds"

UNIT_WATTS = POWER_WATT

COUNTER_ICON = "mdi:counter"


async def async_setup_platform(
    hass: HomeAssistant,
    config: Config,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType,
) -> None:
    """Set up a single GEM temperature sensor."""
    entities: list[GEMSensor] = []
    for monitor_config in discovery_info[CONF_MONITORS]:
        monitor_serial_number = monitor_config[CONF_SERIAL_NUMBER]

        channel_configs = monitor_config[CONF_CHANNELS]
        for sensor in channel_configs:
            entities.append(
                CurrentSensor(
                    monitor_serial_number,
                    sensor[CONF_NUMBER],
                    sensor[CONF_NAME],
                    sensor[CONF_NET_METERING],
                )
            )

        pulse_counter_configs = monitor_config[CONF_PULSE_COUNTERS]
        for sensor in pulse_counter_configs:
            entities.append(
                PulseCounter(
                    monitor_serial_number,
                    sensor[CONF_NUMBER],
                    sensor[CONF_NAME],
                    sensor[CONF_COUNTED_QUANTITY],
                    sensor[CONF_TIME_UNIT],
                    sensor[CONF_COUNTED_QUANTITY_PER_PULSE],
                )
            )

        temperature_sensor_configs = monitor_config[CONF_TEMPERATURE_SENSORS]
        for sensor in temperature_sensor_configs[CONF_SENSORS]:
            entities.append(
                TemperatureSensor(
                    monitor_serial_number,
                    sensor[CONF_NUMBER],
                    sensor[CONF_NAME],
                    temperature_sensor_configs[CONF_TEMPERATURE_UNIT],
                )
            )

        voltage_sensor_configs = monitor_config[CONF_VOLTAGE_SENSORS]
        for sensor in voltage_sensor_configs:
            entities.append(
                VoltageSensor(
                    monitor_serial_number,
                    sensor[CONF_NUMBER],
                    sensor[CONF_NAME],
                )
            )

    async_add_entities(entities)


UnderlyingSensorType = Union[
    greeneye.monitor.Channel,
    greeneye.monitor.PulseCounter,
    greeneye.monitor.TemperatureSensor,
    greeneye.monitor.VoltageSensor,
]


class GEMSensor(SensorEntity):
    """Base class for GreenEye Monitor sensors."""

    _attr_should_poll = False

    def __init__(
        self, monitor_serial_number: int, name: str, sensor_type: str, number: int
    ) -> None:
        """Construct the entity."""
        self._monitor_serial_number = monitor_serial_number
        self._attr_name = name
        self._monitor: greeneye.monitor.Monitor | None = None
        self._sensor_type = sensor_type
        self._number = number
        self._attr_unique_id = (
            f"{self._monitor_serial_number}-{self._sensor_type}-{self._number}"
        )

    async def async_added_to_hass(self) -> None:
        """Wait for and connect to the sensor."""
        monitors = self.hass.data[DATA_GREENEYE_MONITOR]

        if not self._try_connect_to_monitor(monitors):
            monitors.add_listener(self._on_new_monitor)

    def _on_new_monitor(self, monitor: greeneye.monitor.Monitor) -> None:
        monitors = self.hass.data[DATA_GREENEYE_MONITOR]
        if self._try_connect_to_monitor(monitors):
            monitors.remove_listener(self._on_new_monitor)

    async def async_will_remove_from_hass(self) -> None:
        """Remove listener from the sensor."""
        if self._sensor:
            self._sensor.remove_listener(self.async_write_ha_state)
        else:
            monitors = self.hass.data[DATA_GREENEYE_MONITOR]
            monitors.remove_listener(self._on_new_monitor)

    def _try_connect_to_monitor(self, monitors: greeneye.Monitors) -> bool:
        self._monitor = monitors.monitors.get(self._monitor_serial_number)
        if not self._sensor:
            return False

        self._sensor.add_listener(self.async_write_ha_state)
        self.async_write_ha_state()

        return True

    @property
    def _sensor(self) -> UnderlyingSensorType | None:
        raise NotImplementedError()


class CurrentSensor(GEMSensor):
    """Entity showing power usage on one channel of the monitor."""

    _attr_native_unit_of_measurement = UNIT_WATTS
    _attr_device_class = SensorDeviceClass.POWER

    def __init__(
        self, monitor_serial_number: int, number: int, name: str, net_metering: bool
    ) -> None:
        """Construct the entity."""
        super().__init__(monitor_serial_number, name, "current", number)
        self._net_metering = net_metering

    @property
    def _sensor(self) -> greeneye.monitor.Channel | None:
        return self._monitor.channels[self._number - 1] if self._monitor else None

    @property
    def native_value(self) -> float | None:
        """Return the current number of watts being used by the channel."""
        if not self._sensor:
            return None

        return self._sensor.watts

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return total wattseconds in the state dictionary."""
        if not self._sensor:
            return None

        if self._net_metering:
            watt_seconds = self._sensor.polarized_watt_seconds
        else:
            watt_seconds = self._sensor.absolute_watt_seconds

        return {DATA_WATT_SECONDS: watt_seconds}


class PulseCounter(GEMSensor):
    """Entity showing rate of change in one pulse counter of the monitor."""

    _attr_icon = COUNTER_ICON

    def __init__(
        self,
        monitor_serial_number: int,
        number: int,
        name: str,
        counted_quantity: str,
        time_unit: str,
        counted_quantity_per_pulse: float,
    ) -> None:
        """Construct the entity."""
        super().__init__(monitor_serial_number, name, "pulse", number)
        self._counted_quantity_per_pulse = counted_quantity_per_pulse
        self._time_unit = time_unit
        self._attr_native_unit_of_measurement = f"{counted_quantity}/{self._time_unit}"

    @property
    def _sensor(self) -> greeneye.monitor.PulseCounter | None:
        return self._monitor.pulse_counters[self._number - 1] if self._monitor else None

    @property
    def native_value(self) -> float | None:
        """Return the current rate of change for the given pulse counter."""
        if not self._sensor or self._sensor.pulses_per_second is None:
            return None

        result = (
            self._sensor.pulses_per_second
            * self._counted_quantity_per_pulse
            * self._seconds_per_time_unit
        )
        return result

    @property
    def _seconds_per_time_unit(self) -> int:
        """Return the number of seconds in the given display time unit."""
        if self._time_unit == TIME_SECONDS:
            return 1
        if self._time_unit == TIME_MINUTES:
            return 60
        if self._time_unit == TIME_HOURS:
            return 3600

        # Config schema should have ensured it is one of the above values
        raise Exception(
            f"Invalid value for time unit: {self._time_unit}. Expected one of {TIME_SECONDS}, {TIME_MINUTES}, or {TIME_HOURS}"
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return total pulses in the data dictionary."""
        if not self._sensor:
            return None

        return {DATA_PULSES: self._sensor.pulses}


class TemperatureSensor(GEMSensor):
    """Entity showing temperature from one temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE

    def __init__(
        self, monitor_serial_number: int, number: int, name: str, unit: str
    ) -> None:
        """Construct the entity."""
        super().__init__(monitor_serial_number, name, "temp", number)
        self._attr_native_unit_of_measurement = unit

    @property
    def _sensor(self) -> greeneye.monitor.TemperatureSensor | None:
        return (
            self._monitor.temperature_sensors[self._number - 1]
            if self._monitor
            else None
        )

    @property
    def native_value(self) -> float | None:
        """Return the current temperature being reported by this sensor."""
        if not self._sensor:
            return None

        return self._sensor.temperature


class VoltageSensor(GEMSensor):
    """Entity showing voltage."""

    _attr_native_unit_of_measurement = ELECTRIC_POTENTIAL_VOLT
    _attr_device_class = SensorDeviceClass.VOLTAGE

    def __init__(self, monitor_serial_number: int, number: int, name: str) -> None:
        """Construct the entity."""
        super().__init__(monitor_serial_number, name, "volts", number)

    @property
    def _sensor(self) -> greeneye.monitor.VoltageSensor | None:
        """Wire the updates to the monitor itself, since there is no voltage element in the API."""
        return self._monitor.voltage_sensor if self._monitor else None

    @property
    def native_value(self) -> float | None:
        """Return the current voltage being reported by this sensor."""
        if not self._sensor:
            return None

        return self._sensor.voltage
