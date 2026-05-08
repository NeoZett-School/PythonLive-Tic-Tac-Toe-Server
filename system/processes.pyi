"""Functions for internal processes of the `system` module."""

from typing import Any, Optional
from _typeshed import SupportsWrite

def set_appid(appid: str) -> None: 
    """Sets the application ID for the current process on Windows. 
    This is used to group windows and tasks in the taskbar under a common application identity."""

def redirect_except(fp: Optional[SupportsWrite[Any]] = None): 
    """Redirects global error messages into their appropriate logging file."""