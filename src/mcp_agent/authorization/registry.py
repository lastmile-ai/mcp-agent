"""
Keep track of all authorization engines registered with the framework.  Each engine
can have its own concept/implementation of authorization.
"""

from typing import Dict

from mcp_agent.authorization.authorizer import AuthorizationEngine


class AuthorizationRegistry:
    """
    Centralized registration of authorization engines for authorizing entities in
    the framework such as Agent APIs. These are invoked by authorization decorators
    in various APIs and hooks that need authorization.
    """

    def __init__(self):
        # Agent's "list_tools" authorizer registry
        self._engines: Dict[str, AuthorizationEngine] = {}

    def register_authorization_engine(
        self,
        name: str,
        engine: AuthorizationEngine,
    ) -> None:
        """
        Registers authorization engine with the registry

        :param name: Unique name of the authorization engine.
        :param engin: The engine associated with the name.
        """
        if name in self._engines:
            print(f"Authorization engine already registered for '{name}'. Overwriting.")
        self._engines[name] = engine

    def get_authorization_engine(self, name: str) -> AuthorizationEngine | None:
        """
        Retrieves authorization engine with the given name.

        :param name: Unique name of the authorization engine.
        :return: The authorization engine.
        """
        return self._engines.get(name)
