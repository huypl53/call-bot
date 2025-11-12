"""
Base Tool class cho KIAI Assistant
Áp dụng SOLID principles - Interface Segregation & Open/Closed
"""

from abc import ABC, abstractmethod
from typing import Any, Dict

from cti.core.session_manager import SessionManager


class BaseTool(ABC):
    """
    Abstract base class cho tất cả các tools.
    Mọi tool phải implement 2 methods: get_definition() và execute()
    """

    @abstractmethod
    def get_definition(self) -> Dict[str, Any]:
        """
        Trả về OpenAI function definition.

        Returns:
            Dict chứa type, name, description, parameters theo format OpenAI
        """
        pass

    @abstractmethod
    async def execute(self, session_manager: SessionManager, **kwargs) -> Dict[str, Any]:
        """
        Execute tool với arguments được cung cấp.

        Args:
            session_manager: Session manager instance
            **kwargs: Arguments từ OpenAI function call

        Returns:
            Dict chứa kết quả execution
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Tên của tool"""
        pass

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self.name}>"
