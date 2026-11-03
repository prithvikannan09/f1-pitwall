import sys
from pathlib import Path

import streamlit as st

_root = Path(__file__).resolve().parent.parent / "f1analytics"
_stamp = max((p.stat().st_mtime for p in _root.rglob("*.py")), default=0)
if getattr(sys, "_pitwall_code_stamp", _stamp) != _stamp:
    for _name in [m for m in sys.modules if m == "f1analytics" or m.startswith("f1analytics.")]:
        del sys.modules[_name]
    st.cache_data.clear()
    st.cache_resource.clear()
sys._pitwall_code_stamp = _stamp

from f1analytics.ui.pitwall_page import main

main()
