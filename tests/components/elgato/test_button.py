"""Tests for the Elgato Light button platform."""
from unittest.mock import MagicMock

from elgato import ElgatoError
import pytest

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID, ATTR_ICON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory

from tests.common import MockConfigEntry


@pytest.mark.freeze_time("2021-11-13 11:48:00")
async def test_button_identify(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_elgato: MagicMock,
) -> None:
    """Test the Elgato identify button."""
    entity_registry = er.async_get(hass)

    state = hass.states.get("button.identify")
    assert state
    assert state.attributes.get(ATTR_ICON) == "mdi:help"
    assert state.state == STATE_UNKNOWN

    entry = entity_registry.async_get("button.identify")
    assert entry
    assert entry.unique_id == "CN11A1A00001_identify"
    assert entry.entity_category == EntityCategory.CONFIG

    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.identify"},
        blocking=True,
    )

    assert len(mock_elgato.identify.mock_calls) == 1
    mock_elgato.identify.assert_called_with()

    state = hass.states.get("button.identify")
    assert state
    assert state.state == "2021-11-13T11:48:00+00:00"


async def test_button_identify_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_elgato: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test an error occurs with the Elgato identify button."""
    mock_elgato.identify.side_effect = ElgatoError
    await hass.services.async_call(
        BUTTON_DOMAIN,
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.identify"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert len(mock_elgato.identify.mock_calls) == 1
    assert "An error occurred while identifying the Elgato Light" in caplog.text
