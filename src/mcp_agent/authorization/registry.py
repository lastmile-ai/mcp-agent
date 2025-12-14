"""
Keep track of all engines registered with the framework.  Each engine can have
its own concepts/implementations for authorization.
"""

from typing import Dict

from mcp_agent.authorization.authorizer import AuthorizationEngine


class AuthorizationRegistry:
    """
    Centralized registration of authorization points for authorization engines
    These are invoked by authorization decorators in valious APIs and hooks that
    need authorization.
    """

    def __init__(self):
        # Agent's "list_tools" authorizer registry
        self._engines: Dict[str, AuthorizationEngine] = {}

    def register_authorization_engine(
        self,
        name: str,
        engine: AuthorizationEngine,
    ):
        """
        Registers authorization engine with the registry

        :param name: Unique name of the authorization engine.
        :param engin: The engine associated with the name.
        """
        if name in self._engines:
            print(
                "Engine authorizer already registered for '%s'. Overwriting.",
                name,
            )
        self._engines[name] = engine

    def get_authorization_engine(self, name: str) -> AuthorizationEngine:
        """
        Retrieves authorization engine with the given name.

        :param name: Unique name of the authorization engine.
        :return: The authorization engine.
        """
        return self._engines.get(name)
