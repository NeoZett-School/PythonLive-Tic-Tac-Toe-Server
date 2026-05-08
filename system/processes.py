import ctypes
import sys
import traceback
import logging
from datetime import datetime
from contextvars import ContextVar

_except_io = ContextVar("_except_io", default=None)

def set_appid(appid):
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(appid)
    except Exception as e:
        print(f"AppID could not be set: {e}")

def _except_hook(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    f = _except_io.get()
    if f is not None:
        f.write(f"\nError happened at {datetime.now()}\n")
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=f)
    else:
        logging.error(
            "Unhandled exception",
            exc_info=(exc_type, exc_value, exc_traceback)
        )

def redirect_except(fp = None):
    sys.excepthook = _except_hook
    if fp is not None:
        _except_io.set(fp)