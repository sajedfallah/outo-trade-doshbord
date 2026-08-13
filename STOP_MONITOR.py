
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parent
p=ROOT/"storage"/"mt5_monitor.pid"
if not p.exists():
    print("Monitor PID file not found.")
    raise SystemExit(0)
try:
    pid=int(p.read_text().strip())
    proc=psutil.Process(pid)
    proc.terminate()
    proc.wait(timeout=5)
    print("MT5 monitor stopped:",pid)
except Exception as e:
    print("STOP ERROR:",e)
try:p.unlink()
except Exception:pass
