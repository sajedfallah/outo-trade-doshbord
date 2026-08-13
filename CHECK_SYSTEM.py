
import sys
print("PYTHON:",sys.version)
try:
 import streamlit; print("STREAMLIT:",streamlit.__version__)
except Exception as e: print("STREAMLIT ERROR:",e)
try:
 import requests; print("REQUESTS:",requests.__version__)
except Exception as e: print("REQUESTS ERROR:",e)
try:
 import MetaTrader5 as mt5; print("MT5 PACKAGE:",getattr(mt5,"__version__","OK"))
except Exception as e: print("MT5 PACKAGE ERROR:",e)
