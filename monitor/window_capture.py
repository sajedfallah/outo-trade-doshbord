
from pathlib import Path
import time,ctypes,subprocess,json
from ctypes import wintypes

PROCESS_QUERY_LIMITED_INFORMATION=0x1000

def _clamp(v,lo,hi):
    return max(lo,min(hi,float(v)))

def _chart_crop(img,crop_cfg):
    w,h=img.size
    l=_clamp(crop_cfg.get("left",.02),0,.80)
    t=_clamp(crop_cfg.get("top",.055),0,.60)
    r=_clamp(crop_cfg.get("right",.985),.20,1)
    b=_clamp(crop_cfg.get("bottom",.79),.30,1)
    if r<=l+.10:r=min(1,l+.60)
    if b<=t+.10:b=min(1,t+.60)
    box=(int(w*l),int(h*t),int(w*r),int(h*b))
    return img.crop(box),box

def _process_image_path(pid):
    try:
        k32=ctypes.windll.kernel32
        h=k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,False,int(pid))
        if not h:return ""
        try:
            size=wintypes.DWORD(32768)
            buf=ctypes.create_unicode_buffer(size.value)
            if k32.QueryFullProcessImageNameW(h,0,buf,ctypes.byref(size)):
                return buf.value
        finally:
            k32.CloseHandle(h)
    except Exception:
        pass
    return ""

def _enum_all_windows():
    user32=ctypes.windll.user32
    rows=[]
    EnumWindowsProc=ctypes.WINFUNCTYPE(ctypes.c_bool,wintypes.HWND,wintypes.LPARAM)

    def callback(hwnd,lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True

            rect=wintypes.RECT()
            if not user32.GetWindowRect(hwnd,ctypes.byref(rect)):
                return True
            ww,hh=rect.right-rect.left,rect.bottom-rect.top
            if ww<250 or hh<150:
                return True

            pid=wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
            pid=int(pid.value)

            ln=user32.GetWindowTextLengthW(hwnd)
            buf=ctypes.create_unicode_buffer(max(1,ln+1))
            if ln>0:user32.GetWindowTextW(hwnd,buf,ln+1)
            title=buf.value or ""

            clsbuf=ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd,clsbuf,256)
            cls=clsbuf.value or ""

            exe=_process_image_path(pid)

            rows.append({
                "hwnd":int(hwnd),"pid":pid,"title":title,"class":cls,"exe":exe,
                "window_rect":(rect.left,rect.top,rect.right,rect.bottom),
                "width":ww,"height":hh,"area":ww*hh
            })
        except Exception:
            pass
        return True

    cb=EnumWindowsProc(callback)
    user32.EnumWindows(cb,0)
    rows.sort(key=lambda x:x["area"],reverse=True)
    return rows

def _choose_mt5_window(rows,process_names,keywords,class_keywords,terminal_exe_path):
    wanted_names={str(x).lower() for x in (process_names or [])}
    kws=[str(x).lower() for x in (keywords or [])]
    ckws=[str(x).lower() for x in (class_keywords or [])]
    expected=str(terminal_exe_path or "").lower().replace("/","\\")

    scored=[]
    for r in rows:
        exe=(r.get("exe") or "").lower().replace("/","\\")
        name=Path(exe).name.lower() if exe else ""
        title=(r.get("title") or "").lower()
        cls=(r.get("class") or "").lower()

        path_match=bool(expected and exe==expected)
        name_match=name in wanted_names
        title_match=any(k in title for k in kws) if kws else False
        class_match=any(k in cls for k in ckws) if ckws else False

        if not (path_match or name_match or title_match or class_match):
            continue

        score=r["area"]
        if class_match:score+=40_000_000
        if path_match:score+=30_000_000
        if name_match:score+=20_000_000
        if title_match:score+=10_000_000
        rr=dict(r)
        rr.update({
            "path_match":path_match,
            "name_match":name_match,
            "title_match":title_match,
            "class_match":class_match,
            "score":score
        })
        scored.append(rr)

    scored.sort(key=lambda x:x["score"],reverse=True)
    return scored

def _powershell_mainwindow(process_names):
    names=[Path(x).stem for x in (process_names or ["terminal64.exe"])]
    ps_names=",".join("'"+n.replace("'","''")+"'" for n in names)
    script=(
        f"$x=Get-Process -Name {ps_names} -ErrorAction SilentlyContinue | "
        "Where-Object {$_.MainWindowHandle -ne 0} | "
        "Sort-Object @{Expression={$_.MainWindowTitle.Length};Descending=$true} | "
        "Select-Object -First 1 Id,MainWindowHandle,MainWindowTitle,Path | ConvertTo-Json -Compress"
    )
    try:
        r=subprocess.run(["powershell","-NoProfile","-Command",script],
                         capture_output=True,text=True,timeout=8)
        if r.returncode==0 and r.stdout.strip():
            d=json.loads(r.stdout.strip())
            hwnd=int(d.get("MainWindowHandle") or 0)
            if hwnd:
                return {
                    "hwnd":hwnd,"pid":int(d.get("Id") or 0),
                    "title":str(d.get("MainWindowTitle") or ""),
                    "exe":str(d.get("Path") or ""),"class":"",
                    "source":"powershell"
                }
    except Exception:
        pass
    return None

def _restore(hwnd):
    try:
        u=ctypes.windll.user32
        u.ShowWindow(wintypes.HWND(hwnd),9)
        u.SetForegroundWindow(wintypes.HWND(hwnd))
    except Exception:
        pass

def _client_bbox(hwnd):
    try:
        u=ctypes.windll.user32
        r=wintypes.RECT()
        if not u.GetClientRect(wintypes.HWND(hwnd),ctypes.byref(r)):
            return None
        p1=wintypes.POINT(r.left,r.top)
        p2=wintypes.POINT(r.right,r.bottom)
        if not u.ClientToScreen(wintypes.HWND(hwnd),ctypes.byref(p1)):return None
        if not u.ClientToScreen(wintypes.HWND(hwnd),ctypes.byref(p2)):return None
        if p2.x-p1.x<500 or p2.y-p1.y<300:return None
        return (p1.x,p1.y,p2.x,p2.y)
    except Exception:
        return None

def capture_mt5(output_path,keywords=None,delay=.8,
                fallback_full_desktop=False,mode="chart_only",
                chart_crop=None,fallback_mt5_window=True,
                process_names=None,terminal_exe_path=None,
                window_class_keywords=None):
    output_path=Path(output_path)
    output_path.parent.mkdir(parents=True,exist_ok=True)

    keywords=keywords or ["Roco Broker","MetaTrader 5","MetaTrader"]
    process_names=process_names or ["terminal64.exe","terminal.exe"]
    class_keywords=window_class_keywords or ["metaquotes","metatrader"]
    chart_crop=chart_crop or {}

    try:
        from PIL import ImageGrab

        rows=_enum_all_windows()
        candidates=_choose_mt5_window(
            rows,process_names,keywords,class_keywords,terminal_exe_path
        )

        chosen=candidates[0] if candidates else _powershell_mainwindow(process_names)

        if chosen:
            _restore(chosen["hwnd"])
            time.sleep(float(delay))
            bbox=_client_bbox(chosen["hwnd"])
            if bbox:
                whole=ImageGrab.grab(bbox=bbox,all_screens=True)

                if mode=="chart_only":
                    chart,crop_box=_chart_crop(whole,chart_crop)
                    if chart.size[0]>=500 and chart.size[1]>=300:
                        chart.save(output_path)
                        return {
                            "ok":True,"path":str(output_path),
                            "mode":"chart_only_metaquotes",
                            "title":chosen.get("title",""),
                            "class":chosen.get("class",""),
                            "pid":chosen.get("pid"),
                            "exe":chosen.get("exe",""),
                            "class_match":chosen.get("class_match",False),
                            "client_rect":bbox,"crop_box":crop_box,
                            "image_size":chart.size
                        }

                if fallback_mt5_window:
                    whole.save(output_path)
                    return {
                        "ok":True,"path":str(output_path),
                        "mode":"mt5_client_metaquotes",
                        "title":chosen.get("title",""),
                        "class":chosen.get("class",""),
                        "pid":chosen.get("pid"),
                        "exe":chosen.get("exe",""),
                        "client_rect":bbox,"image_size":whole.size
                    }

        # Diagnostic preview: largest visible windows only; no screenshot.
        diag=[]
        for r in rows[:12]:
            diag.append({
                "title":r["title"][:90],
                "class":r["class"][:90],
                "pid":r["pid"],
                "exe":r["exe"][-100:] if r["exe"] else "",
                "size":[r["width"],r["height"]]
            })

        return {
            "ok":False,
            "error":"MT5_MAIN_WINDOW_NOT_FOUND",
            "candidate_count":len(candidates),
            "visible_windows":diag,
            "terminal_exe_path":terminal_exe_path,
            "class_keywords":class_keywords
        }

    except Exception as e:
        return {"ok":False,"error":str(e)}

def capture_preview(output_path,screenshot_cfg):
    return capture_mt5(
        output_path,
        keywords=screenshot_cfg.get("window_title_keywords"),
        process_names=screenshot_cfg.get("process_names",["terminal64.exe","terminal.exe"]),
        terminal_exe_path=screenshot_cfg.get("terminal_exe_path"),
        window_class_keywords=screenshot_cfg.get("window_class_keywords",["metaquotes","metatrader"]),
        delay=screenshot_cfg.get("foreground_delay_seconds",.8),
        fallback_full_desktop=screenshot_cfg.get("fallback_full_desktop",False),
        mode=screenshot_cfg.get("mode","chart_only"),
        chart_crop=screenshot_cfg.get("chart_crop",{}),
        fallback_mt5_window=screenshot_cfg.get("fallback_mt5_window",True)
    )


def capture_current_chart(output_path,cfg):
    """Capture the visible MT5 chart panel without any drawing or redesign."""
    screenshot_cfg=(cfg or {}).get("monitor",{}).get("screenshot",{}) or {}
    if not screenshot_cfg.get("enabled",False):
        return {"ok":False,"error":"MT5_RAW_CHART_CAPTURE_DISABLED"}
    return capture_preview(output_path,screenshot_cfg)
