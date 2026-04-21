"""AirControlBase API client."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)

_LOGIN_ENDPOINT = "/web/user/login"
_DEVICE_DETAILS_ENDPOINT = "/web/userGroup/getDetails"
_CONTROL_ENDPOINT = "/web/device/control"
_SUCCESS_MESSAGES = {
    "\u64cd\u4f5c\u6210\u529f",
    "operation successful",
}
_AUTH_MESSAGES = {
    "token expired",
    "session expired",
    "\u8bf7\u91cd\u65b0\u767b\u5f55",
}
_RATE_LIMIT_HINTS = (
    "too many",
    "rate limit",
    "frequent",
)


class AirControlBaseError(Exception):
    """Base exception for AirControlBase."""


class AirControlBaseAuthError(AirControlBaseError):
    """Exception for authentication errors."""


class AirControlBaseConnectionError(AirControlBaseError):
    """Exception for connectivity errors."""


class AirControlBaseTransientError(AirControlBaseConnectionError):
    """Exception for temporary upstream failures."""


class AirControlBaseRateLimitError(AirControlBaseTransientError):
    """Exception for rate limited requests."""


class AirControlBaseAPI:
    """AirControlBase API client."""

    def __init__(
        self,
        email: str,
        password: str,
        session: aiohttp.ClientSession,
        avoid_refresh_status_on_update_in_ms: int = 5000,
    ) -> None:
        """Initialize the API client."""
        self._email = email
        self._password = password
        self._session = session
        self._base_url = "https://www.aircontrolbase.com"
        self._user_id: str | None = None
        self._last_update_time = 0
        self._avoid_refresh_status_on_update_in_ms = avoid_refresh_status_on_update_in_ms
        self._last_devices: list[dict[str, Any]] = []

    async def login(self) -> None:
        """Login to AirControlBase."""
        payload = {
            "account": self._email,
            "password": self._password,
            "avoidRefreshStatusOnUpdateInMs": self._avoid_refresh_status_on_update_in_ms,
        }

        _LOGGER.debug("Attempting AirControlBase login for %s", self._email)

        try:
            response, result = await self._post_form(_LOGIN_ENDPOINT, payload)
        except AirControlBaseAuthError:
            self._reset_authentication()
            raise
        except AirControlBaseRateLimitError:
            self._reset_authentication()
            raise
        except AirControlBaseTransientError:
            self._reset_authentication()
            raise
        except AirControlBaseConnectionError:
            self._reset_authentication()
            raise

        if not self._is_success_payload(result):
            error_msg = self._error_message(result)
            _LOGGER.error("Login failed with API response: %s", error_msg)
            self._reset_authentication()
            if self._is_auth_failure_payload(result):
                raise AirControlBaseAuthError(f"Login failed: {error_msg}")
            if self._is_rate_limited_payload(result):
                raise AirControlBaseRateLimitError(f"Login rate limited: {error_msg}")
            raise AirControlBaseError(f"Login failed: {error_msg}")

        user_id = result.get("result", {}).get("id")
        if not user_id:
            _LOGGER.error("Login response did not include user id: %s", result)
            self._reset_authentication()
            raise AirControlBaseAuthError("No user id in login response")

        self._user_id = str(user_id)
        _LOGGER.info(
            "Successfully authenticated with AirControlBase (user id %s)",
            self._user_id,
        )
        _LOGGER.debug("Login response headers: %s", dict(response.headers))

    async def _post_form(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> tuple[aiohttp.ClientResponse, dict[str, Any]]:
        """Send a form-encoded POST request and parse the JSON body."""
        url = f"{self._base_url}{endpoint}"
        _LOGGER.debug("POST %s", endpoint)

        try:
            async with async_timeout.timeout(10):
                async with self._session.post(url, data=payload) as response:
                    _LOGGER.debug("%s returned HTTP %s", endpoint, response.status)

                    if response.status in (401, 403):
                        raise AirControlBaseAuthError(f"HTTP error {response.status}")
                    if response.status == 429:
                        raise AirControlBaseRateLimitError(f"HTTP error {response.status}")
                    if response.status in (408, 425) or 500 <= response.status < 600:
                        raise AirControlBaseTransientError(f"HTTP error {response.status}")
                    if response.status != 200:
                        raise AirControlBaseConnectionError(f"HTTP error {response.status}")

                    result = await self._parse_json_response(response, endpoint)
                    return response, result
        except asyncio.TimeoutError as err:
            raise AirControlBaseTransientError(f"Timeout calling {endpoint}") from err
        except aiohttp.ClientError as err:
            raise AirControlBaseTransientError(f"Client error calling {endpoint}: {err}") from err

    async def _parse_json_response(
        self,
        response: aiohttp.ClientResponse,
        endpoint: str,
    ) -> dict[str, Any]:
        """Parse a JSON response and log the raw body if it is invalid."""
        try:
            result = await response.json(content_type=None)
        except Exception as err:
            text_result = await response.text()
            _LOGGER.error(
                "Invalid JSON response from %s: %s. Raw response: %s",
                endpoint,
                err,
                text_result,
            )
            raise AirControlBaseConnectionError(
                f"Invalid response format from {endpoint}: {err}"
            ) from err

        if not isinstance(result, dict):
            _LOGGER.error("Unexpected payload type from %s: %s", endpoint, type(result))
            raise AirControlBaseConnectionError(
                f"Unexpected response type from {endpoint}: {type(result).__name__}"
            )

        _LOGGER.debug("%s response payload: %s", endpoint, result)
        return result

    async def _request(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        """Send a request with automatic re-authentication."""
        if not self._user_id:
            await self.login()

        request_payload = {
            "userId": self._user_id or "",
            **payload,
        }

        try:
            _, result = await self._post_form(endpoint, request_payload)
        except AirControlBaseAuthError as err:
            if retry_auth:
                _LOGGER.warning(
                    "Authentication failed for %s. Resetting session and retrying once.",
                    endpoint,
                )
                self._reset_authentication()
                await self.login()
                return await self._request(endpoint, payload, retry_auth=False)
            raise

        if self._is_auth_failure_payload(result):
            error_msg = self._error_message(result)
            if retry_auth:
                _LOGGER.warning(
                    "Session expired during %s (%s). Re-authenticating once.",
                    endpoint,
                    error_msg,
                )
                self._reset_authentication()
                await self.login()
                return await self._request(endpoint, payload, retry_auth=False)
            raise AirControlBaseAuthError(f"Authentication failed: {error_msg}")

        if self._is_rate_limited_payload(result):
            error_msg = self._error_message(result)
            raise AirControlBaseRateLimitError(f"Request rate limited: {error_msg}")

        if not self._is_success_payload(result):
            error_msg = self._error_message(result)
            raise AirControlBaseError(f"API error: {error_msg}")

        return result

    def _reset_authentication(self) -> None:
        """Clear the cached authentication state."""
        if self._user_id:
            _LOGGER.debug("Resetting cached AirControlBase authentication state")
        self._user_id = None

    def _is_success_payload(self, payload: dict[str, Any]) -> bool:
        """Return True when the API payload indicates success."""
        code = payload.get("code")
        message = self._normalize_message(payload.get("msg") or payload.get("message"))
        return code in ("200", 200) or message in _SUCCESS_MESSAGES

    def _is_auth_failure_payload(self, payload: dict[str, Any]) -> bool:
        """Return True when the payload indicates an authentication failure."""
        code = payload.get("code")
        message = self._normalize_message(payload.get("msg") or payload.get("message"))
        return code in ("401", 401, "403", 403) or message in _AUTH_MESSAGES

    def _is_rate_limited_payload(self, payload: dict[str, Any]) -> bool:
        """Return True when the payload indicates a rate limit response."""
        code = payload.get("code")
        message = self._normalize_message(payload.get("msg") or payload.get("message"))
        return code in ("429", 429) or any(hint in message for hint in _RATE_LIMIT_HINTS)

    def _normalize_message(self, message: Any) -> str:
        """Normalize an API message for comparisons."""
        return str(message or "").strip().lower()

    def _error_message(self, payload: dict[str, Any]) -> str:
        """Extract an error message from a payload."""
        return str(
            payload.get("msg")
            or payload.get("message")
            or f"Unknown error (code: {payload.get('code')})"
        )

    def _extract_devices(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract all device records from the payload."""
        devices: list[dict[str, Any]] = []
        for area in payload.get("result", {}).get("areas", []):
            devices.extend(area.get("data", []))
        self._last_devices = devices
        _LOGGER.debug("Parsed %s devices from API payload", len(devices))
        return devices

    async def control_device(
        self,
        control: dict[str, Any],
        operation: dict[str, Any],
    ) -> None:
        """Control a device."""
        self._last_update_time = int(time.time() * 1000)
        # The cloud API expects the complete target device state. Sending only
        # the diff can return success while the next poll shows no real change.
        control_payload = {**control, **operation} if control else dict(operation)
        form_payload = {
            "control": json.dumps(control_payload),
            "operation": json.dumps(control_payload),
        }

        _LOGGER.debug(
            "Sending control request for device %s with updated keys %s",
            control_payload.get("id"),
            sorted(operation.keys()),
        )
        _LOGGER.debug(
            "AirControlBase target state for device %s: power=%s mode=%s setTemp=%s "
            "wind=%s swing=%s",
            control_payload.get("id"),
            control_payload.get("power"),
            control_payload.get("mode"),
            control_payload.get("setTemp"),
            control_payload.get("wind"),
            control_payload.get("swing"),
        )
        await self._request(_CONTROL_ENDPOINT, form_payload)

    async def get_devices(self) -> list[dict[str, Any]]:
        """Get all devices, reusing cached data shortly after writes."""
        if (
            self._last_update_time > 0
            and int(time.time() * 1000) - self._last_update_time
            < self._avoid_refresh_status_on_update_in_ms
        ):
            _LOGGER.debug("Returning cached devices because a control update was just sent")
            return list(self._last_devices)

        return await self.get_details()

    async def get_details(self) -> list[dict[str, Any]]:
        """Fetch device details from the API."""
        result = await self._request(_DEVICE_DETAILS_ENDPOINT, {})
        return self._extract_devices(result)

    async def getDetails(self) -> list[dict[str, Any]]:
        """Backward-compatible wrapper for device details."""
        return await self.get_details()

    async def test_connection(self) -> bool:
        """Test whether authentication and device retrieval are working."""
        await self.login()
        await self.get_details()
        return True

    async def ensure_authenticated(self) -> None:
        """Ensure the API client is authenticated."""
        if not self._user_id:
            _LOGGER.warning("No cached AirControlBase session. Logging in again.")
            await self.login()
