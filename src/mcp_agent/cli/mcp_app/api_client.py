"""MCP App API client implementation for the MCP Agent Cloud API."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Union
from urllib.parse import urlparse

from pydantic import BaseModel

from mcp_agent.cli.core.api_client import APIClient


class AppServerInfo(BaseModel):
    serverUrl: str
    status: Literal[
        "APP_SERVER_STATUS_UNSPECIFIED",
        "APP_SERVER_STATUS_ONLINE",
        "APP_SERVER_STATUS_OFFLINE",
    ]  # Enums: 0=UNSPECIFIED, 1=ONLINE, 2=OFFLINE


# A developer-deployed MCP App which others can configure and use.
class MCPApp(BaseModel):
    appId: str
    name: str
    creatorId: str
    description: Optional[str] = None
    createdAt: datetime
    updatedAt: datetime
    appServerInfo: Optional[AppServerInfo] = None
    deploymentMetadata: Optional[Dict[str, Any]] = None


# A user-configured MCP App 'instance', created by configuring a deployed MCP App.
class MCPAppConfiguration(BaseModel):
    appConfigurationId: str
    app: Optional[MCPApp] = None
    creatorId: str
    createdAt: Optional[datetime] = None
    appServerInfo: Optional[AppServerInfo] = None


class ListAppsResponse(BaseModel):
    apps: Optional[
        List[MCPApp]
    ] = []  # Proto treats empty list and 0 and undefined so must be optional!
    nextPageToken: Optional[str] = None
    totalCount: Optional[int] = 0


class ListAppConfigurationsResponse(BaseModel):
    appConfigurations: Optional[
        List[MCPAppConfiguration]
    ] = []  # Proto treats empty list and 0 and undefined so must be optional!
    nextPageToken: Optional[str] = None
    totalCount: Optional[int] = 0


class CanDoActionCheck(BaseModel):
    action: str
    canDoAction: Optional[bool] = False


class CanDoActionsResponse(BaseModel):
    canDoActions: Optional[List[CanDoActionCheck]] = []


APP_ID_PREFIX = "app_"
APP_CONFIG_ID_PREFIX = "apcnf_"


def is_valid_app_id_format(app_id: str) -> bool:
    """Check if the given app ID has a valid format.

    Args:
        app_id: The app ID to validate

    Returns:
        bool: True if the app ID is a valid format, False otherwise
    """
    return app_id.startswith(APP_ID_PREFIX)


def is_valid_app_config_id_format(app_config_id: str) -> bool:
    """Check if the given app configuration ID has a valid format.

    Args:
        app_config_id: The app configuration ID to validate

    Returns:
        bool: True if the app configuration ID is a valid format, False otherwise
    """
    return app_config_id.startswith(APP_CONFIG_ID_PREFIX)


def is_valid_server_url_format(server_url: str) -> bool:
    """Check if the given server URL has a valid format.

    Args:
        server_url: The server URL to validate

    Returns:
        bool: True if the server URL is a valid format, False otherwise
    """
    parsed = urlparse(server_url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


class LogEntry(BaseModel):
    """Represents a single log entry."""

    timestamp: Optional[str] = None
    level: Optional[str] = None
    message: Optional[str] = None
    # Allow additional fields that might be present

    class Config:
        extra = "allow"


class GetAppLogsResponse(BaseModel):
    """Response from get_app_logs API endpoint."""

    logEntries: Optional[List[LogEntry]] = []

    @property
    def log_entries_list(self) -> List[LogEntry]:
        """Get log entries regardless of field name format."""
        return self.logEntries or []


class MCPAppClient(APIClient):
    """Client for interacting with the MCP App API service over HTTP."""

    async def create_app(self, name: str, description: Optional[str] = None) -> MCPApp:
        """Create a new MCP App via the API.

        Args:
            name: The name of the MCP App
            description: Optional description for the app

        Returns:
            MCPApp: The created MCP App

        Raises:
            ValueError: If the name is empty or invalid
            httpx.HTTPError: If the API request fails
        """
        if not name or not isinstance(name, str):
            raise ValueError("App name must be a non-empty string")

        payload: Dict[str, Any] = {
            "name": name,
        }

        if description:
            payload["description"] = description

        response = await self.post("/mcp_app/create_app", payload)

        res = response.json()
        if not res or "app" not in res:
            raise ValueError("API response did not contain the created app data")

        return MCPApp(**res["app"])

    async def get_app(
        self, app_id: Optional[str] = None, server_url: Optional[str] = None
    ) -> MCPApp:
        """Get an MCP App by its ID or server URL via the API.

        Args:
            app_id: The UUID of the app to retrieve
            server_url: The server URL of the app to retrieve

        Returns:
            MCPApp: The retrieved MCP App

        Raises:
            ValueError: If the app_id or server_url is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        if (app_id and server_url) or (not app_id and not server_url):
            raise ValueError("One of app_id or server_url must be provided")

        request_data = {}

        if app_id:
            if not is_valid_app_id_format(app_id):
                raise ValueError(f"Invalid app ID format: {app_id}")
            request_data["appId"] = app_id
        elif server_url:
            if not is_valid_server_url_format(server_url):
                raise ValueError(f"Invalid server URL format: {server_url}")
            request_data["appServerUrl"] = server_url

        response = await self.post("/mcp_app/get_app", request_data)

        res = response.json()
        if not res or "app" not in res:
            raise ValueError("API response did not contain the app data")

        return MCPApp(**res["app"])

    async def get_app_configuration(
        self,
        app_config_id: Optional[str] = None,
        server_url: Optional[str] = None,
    ) -> MCPAppConfiguration:
        """Get an MCP App Configuration by its ID or server URL via the API.

        Args:
            app_config_id: The UUID of the app configuration to retrieve
            server_url: The server URL of the app configuration to retrieve

        Returns:
            MCPAppConfiguration: The retrieved MCP App Configuration

        Raises:
            ValueError: If the app_config_id or server_url is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        if (app_config_id and server_url) or (not app_config_id and not server_url):
            raise ValueError("One of app_config_id or server_url must be provided")

        request_data = {}

        if app_config_id:
            if not is_valid_app_config_id_format(app_config_id):
                raise ValueError(
                    f"Invalid app configuration ID format: {app_config_id}"
                )
            request_data["appConfigurationId"] = app_config_id
        elif server_url:
            if not is_valid_server_url_format(server_url):
                raise ValueError(f"Invalid server URL format: {server_url}")
            request_data["appConfigServerUrl"] = server_url

        response = await self.post("/mcp_app/get_app_configuration", request_data)

        res = response.json()
        if not res or "appConfiguration" not in res:
            raise ValueError("API response did not contain the configured app data")

        return MCPAppConfiguration(**res["appConfiguration"])

    async def get_app_or_config(
        self, app_id_or_url: str
    ) -> Union[MCPApp, MCPAppConfiguration]:
        """Get an MCP App or App Configuration by its ID or server URL.

        This method will first try to retrieve the app by ID, and if that fails,
        it will attempt to retrieve it by server URL.

        Args:
            app_id_or_url: The UUID or server URL of the app or configuration

        Returns:
            MCPApp: The retrieved MCP App

        Raises:
            ValueError: If the app_id_or_url is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """

        if is_valid_app_id_format(app_id_or_url):
            return await self.get_app(app_id=app_id_or_url)
        elif is_valid_app_config_id_format(app_id_or_url):
            return await self.get_app_configuration(app_config_id=app_id_or_url)
        else:
            try:
                # Try to get as an app first
                return await self.get_app(server_url=app_id_or_url)
            except Exception:
                pass
            try:
                # If that fails, try to get as a configuration
                return await self.get_app_configuration(server_url=app_id_or_url)
            except Exception as e:
                raise ValueError(
                    f"Failed to retrieve app or configuration for ID or server URL: {app_id_or_url}"
                ) from e

    async def get_app_id_by_name(self, name: str) -> Optional[str]:
        """Get the app ID for a given app name via the API.

        Args:
            name: The name of the MCP App

        Returns:
            Optional[str]: The UUID of the MCP App, or None if not found

        Raises:
            ValueError: If the name is empty or invalid
            httpx.HTTPStatusError: If the API returns an error
            httpx.HTTPError: If the request fails
        """
        if not name or not isinstance(name, str):
            raise ValueError(f"Invalid app name format: {name}")

        apps = await self.list_apps(name_filter=name, max_results=10)
        if not apps.apps:
            return None

        # Return the app with exact name match
        return next((app.appId for app in apps.apps if app.name == name), None)

    async def deploy_app(
        self,
        app_id: str,
        deployment_metadata: Optional[Dict[str, Any]] = None,
    ) -> MCPApp:
        """Deploy an MCP App via the API.

        Args:
            app_id: The UUID of the app to deploy

        Returns:
            MCPApp: The deployed MCP App

        Raises:
            ValueError: If the app_id or source_uri is invalid
            httpx.HTTPStatusError: If the API returns an error
            httpx.HTTPError: If the request fails
        """
        if not app_id or not is_valid_app_id_format(app_id):
            raise ValueError(f"Invalid app ID format: {app_id}")

        payload: Dict[str, Any] = {"appId": app_id}
        if deployment_metadata:
            # Tentative field; include only when requested
            payload["deploymentMetadata"] = deployment_metadata

        # Use a longer timeout for deployments
        deploy_timeout = 300.0
        response = await self.post(
            "/mcp_app/deploy_app", payload, timeout=deploy_timeout
        )

        res = response.json()
        if not res or "app" not in res:
            raise ValueError("API response did not contain the app data")

        return MCPApp(**res["app"])

    async def configure_app(
        self,
        app_server_url: str,
        config_params: Dict[str, Any] = {},
    ) -> MCPAppConfiguration:
        """Configure a deployed MCP App via the API.

        Args:
            app_server_url: The server URL of the app to configure
            config_params: Dictionary of configuration parameters (e.g. user secrets)

        Returns:
            MCPAppConfiguration: The configured MCP App

        Raises:
            ValueError: If the app_id or config_params is invalid
            httpx.HTTPStatusError: If the API returns an error
            httpx.HTTPError: If the request fails
        """
        if not app_server_url or not is_valid_server_url_format(app_server_url):
            raise ValueError(f"Invalid app server URL format: {app_server_url}")

        payload = {
            "appServerUrl": app_server_url,
            "params": config_params,
        }

        response = await self.put("/mcp_app/configure_app", payload)

        res = response.json()
        if not res or "appConfiguration" not in res:
            raise ValueError("API response did not contain the configured app data")

        return MCPAppConfiguration(**res["appConfiguration"])

    async def list_config_params(self, app_server_url: str) -> List[str]:
        """List required configuration parameters (e.g. user secrets) for an MCP App via the API.

        Args:
            app_server_url: The server URL of the app to retrieve config params for

        Returns:
            List[str]: List of configuration parameter names

        Raises:
            ValueError: If the app_id is invalid
            httpx.HTTPStatusError: If the API returns an error
            httpx.HTTPError: If the request fails
        """
        if not app_server_url or not is_valid_server_url_format(app_server_url):
            raise ValueError(f"Invalid app server URL format: {app_server_url}")

        response = await self.post(
            "/mcp_app/list_config_params", {"appServerUrl": app_server_url}
        )
        return response.json().get("paramKeys", [])

    async def list_apps(
        self,
        name_filter: Optional[str] = None,
        max_results: int = 100,
        page_token: Optional[str] = None,
    ) -> ListAppsResponse:
        """List MCP Apps via the API.
        Args:
            name_filter: Optional filter for app names
            max_results: Maximum number of results to return (default 100)
            page_token: Optional token for pagination
        Returns:
            ListAppsResponse: List of MCP Apps with pagination info
        Raises:
            httpx.HTTPStatusError: If the API returns an error
            httpx.HTTPError: If the request fails
        """
        # Prepare request payload
        payload: Dict[str, Any] = {
            "maxResults": max_results,
            "isCreator": True,  # Only list apps created by the user
        }

        if page_token:
            payload["pageToken"] = page_token

        if name_filter:
            payload["nameFilter"] = name_filter

        response = await self.post("/mcp_app/list_apps", payload)
        return ListAppsResponse(**response.json())

    async def list_app_configurations(
        self,
        name_filter: Optional[str] = None,
        max_results: int = 100,
        page_token: Optional[str] = None,
    ) -> ListAppConfigurationsResponse:
        """List MCP App configurations via the API.

        Args:
            name_filter: Optional filter for app names
            max_results: Maximum number of results to return (default 100)
            page_token: Optional token for pagination

        Returns:
            ListAppsResponse: List of MCP App configurations with pagination info

        Raises:
            httpx.HTTPStatusError: If the API returns an error
            httpx.HTTPError: If the request fails
        """
        # Prepare request payload
        payload: Dict[str, Any] = {
            "maxResults": max_results,
            "isCreator": True,  # Only list configurations created by the user
        }

        if page_token:
            payload["pageToken"] = page_token

        if name_filter:
            payload["nameFilter"] = name_filter

        response = await self.post("/mcp_app/list_app_configurations", payload)
        return ListAppConfigurationsResponse(**response.json())

    async def delete_app(self, app_id: str) -> str:
        """Delete an MCP App via the API.

        Args:
            app_id: The UUID of the app to delete

        Returns:
            str: The ID of the deleted app

        Raises:
            ValueError: If the app_id is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        if not app_id or not is_valid_app_id_format(app_id):
            raise ValueError(f"Invalid app ID format: {app_id}")

        # Prepare request payload
        payload = {
            "appId": app_id,
        }

        response = await self.delete("/mcp_app/delete_app", payload)

        # Parse the response to get the deleted app ID
        data = response.json()
        deleted_id = data.get("appId")

        if not deleted_id:
            raise ValueError("API didn't return the ID of the deleted app")

        return deleted_id

    async def delete_app_configuration(self, app_config_id: str) -> str:
        """Delete an MCP App Configuration via the API.

        Args:
            app_config_id: The UUID of the app configuration to delete

        Returns:
            str: The ID of the deleted app configuration

        Raises:
            ValueError: If the app_configuration_id is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        if not app_config_id or not is_valid_app_config_id_format(app_config_id):
            raise ValueError(f"Invalid app configuration ID format: {app_config_id}")

        # Prepare request payload
        payload = {
            "appConfigId": app_config_id,
        }

        response = await self.delete("/mcp_app/delete_app_configuration", payload)

        # Parse the response to get the deleted app config ID
        data = response.json()
        deleted_id = data.get("appConfigId")

        if not deleted_id:
            raise ValueError(
                "API didn't return the ID of the deleted app configuration"
            )

        return deleted_id

    async def _can_do_action(self, resource_name: str, action: str) -> bool:
        """Check if the viewer can perform a specific action on a resource via the API.
        Args:
            resource_name: The resource name to check permissions for (e.g., "MCP_APP:{app_id}")
            action: The action to check (e.g., "MANAGE:MCP_APP")
        Returns:
            bool: True if the viewer can perform the action, False otherwise
        Raises:
            ValueError: If the resource_name or action is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        if not resource_name or not isinstance(resource_name, str):
            raise ValueError(f"Invalid resource name format: {resource_name}")

        if not action or not isinstance(action, str):
            raise ValueError(f"Invalid action format: {action}")

        # Prepare request payload
        payload = {
            "resourceName": resource_name,
            "actions": [action],
        }

        response = await self.post("/resource_permission/can_viewer_do", payload)

        # Parse the response to check permission
        checks = CanDoActionsResponse(**response.json())

        return any(
            check.action == action and check.canDoAction
            for check in checks.canDoActions or []
        )

    async def can_delete_app(self, app_id: str) -> bool:
        """Check if the viewer can delete an MCP App via the API.

        Args:
            app_id: The UUID of the app to check delete permissions for

        Returns:
            bool: True if the viewer can delete the app, False otherwise

        Raises:
            ValueError: If the app_id is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        if not app_id or not is_valid_app_id_format(app_id):
            raise ValueError(f"Invalid app ID format: {app_id}")

        return await self._can_do_action(
            resource_name=f"MCP_APP:{app_id}",
            action="MANAGE:MCP_APP",
        )

    async def can_delete_app_configuration(self, app_config_id: str) -> bool:
        """Check if the viewer can delete an MCP App Configuration via the API.

        Args:
            app_config_id: The UUID of the app configuration to check delete permissions for

        Returns:
            bool: True if the viewer can delete the app configuration, False otherwise

        Raises:
            ValueError: If the app_configuration_id is invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        if not app_config_id or not is_valid_app_config_id_format(app_config_id):
            raise ValueError(f"Invalid app configuration ID format: {app_config_id}")

        return await self._can_do_action(
            resource_name=f"MCP_APP_CONFIG:{app_config_id}",
            action="MANAGE:MCP_APP_CONFIG",
        )

    async def get_app_logs(
        self,
        app_id: Optional[str] = None,
        app_configuration_id: Optional[str] = None,
        since: Optional[str] = None,
        limit: Optional[int] = None,
        order_by: Optional[str] = None,
        order: Optional[str] = None,
    ) -> GetAppLogsResponse:
        """Get logs for an MCP App or App Configuration via the API.

        Args:
            app_id: The UUID of the app to get logs for (mutually exclusive with app_configuration_id)
            app_configuration_id: The UUID of the app configuration to get logs for (mutually exclusive with app_id)
            since: Time filter for logs (e.g., "1h", "24h", "7d")
            limit: Maximum number of log entries to return
            order_by: Field to order by ("LOG_ORDER_BY_TIMESTAMP" or "LOG_ORDER_BY_LEVEL")
            order: Log ordering direction ("LOG_ORDER_ASC" or "LOG_ORDER_DESC")

        Returns:
            GetAppLogsResponse: The retrieved log entries

        Raises:
            ValueError: If neither or both app_id and app_configuration_id are provided, or if IDs are invalid
            httpx.HTTPStatusError: If the API returns an error (e.g., 404, 403)
            httpx.HTTPError: If the request fails
        """
        # Validate inputs
        if not app_id and not app_configuration_id:
            raise ValueError("Either app_id or app_configuration_id must be provided")
        if app_id and app_configuration_id:
            raise ValueError(
                "Only one of app_id or app_configuration_id can be provided"
            )

        if app_id and not is_valid_app_id_format(app_id):
            raise ValueError(f"Invalid app ID format: {app_id}")
        if app_configuration_id and not is_valid_app_config_id_format(
            app_configuration_id
        ):
            raise ValueError(
                f"Invalid app configuration ID format: {app_configuration_id}"
            )

        # Prepare request payload
        payload = {}
        if app_id:
            payload["app_id"] = app_id
        if app_configuration_id:
            payload["app_configuration_id"] = app_configuration_id
        if since:
            payload["since"] = since
        if limit:
            payload["limit"] = limit
        if order_by:
            payload["order_by"] = order_by
        if order:
            payload["order"] = order

        response = await self.post("/mcp_app/get_app_logs", payload)

        # Parse the response
        data = response.json()
        return GetAppLogsResponse(**data)
