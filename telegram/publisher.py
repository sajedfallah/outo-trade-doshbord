
import json,time
from pathlib import Path
import requests

from config_loader import load_config

ROOT=Path(__file__).resolve().parent.parent


class TelegramDeliveryError(RuntimeError):
    def __init__(self,message,*,ambiguous=False,retryable=True):
        super().__init__(message)
        self.ambiguous=bool(ambiguous)
        self.retryable=bool(retryable)

def _creds():
    cfg=load_config(require_telegram=True)
    token=cfg["telegram"]["bot_token"].strip()
    chat=str(cfg["telegram"]["channel_id"]).strip()
    return token,chat

def get_me(timeout=15):
    token,_=_creds()
    r=requests.get(f"https://api.telegram.org/bot{token}/getMe",timeout=timeout)
    d=r.json()
    if not d.get("ok"):
        raise TelegramDeliveryError(f"Telegram getMe failed: {d}",retryable=False)
    return d

def send_photo(image_path,caption,reply_to_message_id=None,timeout=35,retries=3):
    token,chat=_creds()
    p=Path(image_path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    last=None
    for attempt in range(retries):
        try:
            data={"chat_id":chat,"caption":caption}
            if reply_to_message_id:
                data["reply_parameters"]=json.dumps({"message_id":int(reply_to_message_id)})
            with p.open("rb") as f:
                r=requests.post(
                    f"https://api.telegram.org/bot{token}/sendPhoto",
                    data=data,
                    files={"photo":(p.name,f)},
                    timeout=timeout
                )
            d=r.json()
            if d.get("ok"):
                return d
            last=TelegramDeliveryError(f"Telegram sendPhoto failed: {d}",ambiguous=False,retryable=True)
        except requests.RequestException as e:
            last=TelegramDeliveryError(f"Telegram sendPhoto network failure: {type(e).__name__}",ambiguous=True)
        except Exception as e:last=e
        if attempt<retries-1:
            time.sleep(1.2*(attempt+1))
    raise last


def send_message(text,reply_to_message_id=None,timeout=35,retries=3):
    token,chat=_creds()
    last=None
    for attempt in range(retries):
        try:
            data={"chat_id":chat,"text":text}
            if reply_to_message_id:
                data["reply_parameters"]=json.dumps({"message_id":int(reply_to_message_id)})
            r=requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=data,timeout=timeout
            )
            d=r.json()
            if d.get("ok"):
                return d
            last=TelegramDeliveryError(f"Telegram sendMessage failed: {d}",ambiguous=False,retryable=True)
        except requests.RequestException as e:
            last=TelegramDeliveryError(f"Telegram sendMessage network failure: {type(e).__name__}",ambiguous=True)
        except Exception as e:last=e
        if attempt<retries-1:
            time.sleep(1.2*(attempt+1))
    raise last
