"""Config flow for Chore Race."""

from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import CONFIG_ENTRY_UNIQUE_ID, DOMAIN


class ChoreRaceConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the single local Chore Race instance."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle setup without YAML or credentials."""
        await self.async_set_unique_id(CONFIG_ENTRY_UNIQUE_ID)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Chore Race", data={})
        return self.async_show_form(step_id="user")
