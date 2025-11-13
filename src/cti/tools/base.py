"""
Base Tool class cho KIAI Assistant
Áp dụng SOLID principles - Interface Segregation & Open/Closed
"""

import inspect
from abc import ABC, abstractmethod
from typing import Annotated, Any, Dict, get_args, get_origin, get_type_hints

from cti.core.session_manager import SessionManager


def get_openai_schema(func, name: str = None, description: str = None) -> Dict[str, Any]:
    """Extract OpenAI-compatible function schema from annotated function."""
    sig = inspect.signature(func)
    hints = get_type_hints(func, include_extras=True)

    # Extract description from parameter or docstring
    if description is None:
        description = inspect.getdoc(func) or ""

    # Use function name if not provided
    if name is None:
        name = func.__name__

    # Primitive types we support
    PRIMITIVE_TYPES = {str, int, float, bool, list, dict}

    properties = {}
    required = []

    for param_name, param in sig.parameters.items():
        # Skip self and session_manager
        if param_name in ('self', 'session_manager'):
            continue

        # Skip **kwargs
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            continue

        annotation = hints.get(param_name)

        if annotation is None:
            continue

        # Handle nested Optional[Annotated[...]] structure
        # When a parameter has a default value, Python wraps it as Optional[...]
        from typing import Union
        
        desc = ""
        base_type = annotation
        
        # First, unwrap Optional if present (for parameters with default values)
        origin = get_origin(base_type)
        if origin is Union:
            union_args = get_args(base_type)
            if type(None) in union_args:
                # Extract the non-None type
                non_none_types = [arg for arg in union_args if arg is not type(None)]
                if non_none_types:
                    base_type = non_none_types[0]
                else:
                    base_type = str

        # Extract base type and description from Annotated
        if get_origin(base_type) is Annotated:
            args = get_args(base_type)
            base_type = args[0]
            # Get description from Annotated metadata (second argument)
            if len(args) > 1:
                desc = args[1] if isinstance(args[1], str) else ""

        # Handle Optional inside Annotated (e.g., Annotated[Optional[str], "desc"])
        origin = get_origin(base_type)
        if origin is Union:
            union_args = get_args(base_type)
            # Check if it's Optional (Union with None)
            if type(None) in union_args:
                # Extract the non-None type
                non_none_types = [arg for arg in union_args if arg is not type(None)]
                if non_none_types:
                    base_type = non_none_types[0]
                else:
                    base_type = str

        # Skip non-primitive types
        if base_type not in PRIMITIVE_TYPES:
            continue

        # Map Python types to JSON schema types
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }

        properties[param_name] = {
            "type": type_map[base_type],
            "description": desc
        }

        # Add to required if no default value
        if param.default == inspect.Parameter.empty:
            required.append(param_name)

    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required
        }
    }


class BaseTool(ABC):
    """
    Abstract base class cho tất cả các tools.
    Mọi tool phải implement 2 methods: get_definition() và execute()
    """


    def get_definition(self) -> Dict[str, Any]:
        """
        Trả về OpenAI function definition.
        Default implementation extracts from execute method annotations.
        Can be overridden if needed.

        Returns:
            Dict chứa type, name, description, parameters theo format OpenAI
        """
        return get_openai_schema(self.execute, name=self.name)

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
