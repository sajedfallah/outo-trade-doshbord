"""Durable Telegram outbox delivery for signals, lifecycle updates, and reports."""
from __future__ import annotations

from storage.repo import (
    due_outbox,get_outbox_item,mark_outbox_sending,mark_outbox_sent,
    mark_outbox_failed,update_event_message,update_signal,recover_interrupted_outbox
    ,save_report_run
)
from telegram.publisher import send_message,send_photo,TelegramDeliveryError


def deliver_item(item_or_id,*,send_message_fn=send_message,send_photo_fn=send_photo):
    item=get_outbox_item(item_id=item_or_id) if isinstance(item_or_id,int) else item_or_id
    if item and 'payload' not in item:item=get_outbox_item(item_id=item['id'])
    if not item:return {'sent':False,'reason':'NOT_FOUND'}
    if item.get('status')=='SENT':return {'sent':True,'already_sent':True,'message_id':item.get('telegram_message_id')}
    if item.get('status') in ('UNKNOWN','DEAD'):return {'sent':False,'reason':item.get('status')}
    if not mark_outbox_sending(item['id']):return {'sent':False,'reason':'NOT_CLAIMED'}
    payload=item.get('payload') or {}
    try:
        reply=payload.get('reply_to_message_id')
        if payload.get('image_path'):
            response=send_photo_fn(payload['image_path'],payload.get('text',''),reply_to_message_id=reply)
        else:
            response=send_message_fn(payload.get('text',''),reply_to_message_id=reply)
        mid=int(response['result']['message_id'])
        mark_outbox_sent(item['id'],mid)
        sid=item.get('signal_id');event_key=payload.get('event_key')
        if event_key:
            update_event_message(event_key,mid,payload.get('image_path'))
            if sid:update_signal(sid,last_event_message_id=mid)
        elif sid and item.get('operation_type')=='TELEGRAM_SIGNAL':
            update_signal(sid,telegram_message_id=mid,publication_status='SENT',telegram_error=None)
        if item.get('operation_type')=='TELEGRAM_REPORT' and payload.get('report_record'):
            record=dict(payload['report_record']);record['telegram_message_id']=mid;save_report_run(record)
            try:
                from monitor.workflow import audit
                for report_sid in payload.get('signal_ids',[]):
                    audit(report_sid,'REPORT_INCLUDED','DONE',f"{report_sid}:REPORT_INCLUDED:{record['report_key']}",source='REPORT_ENGINE',detail=f"{record['report_type']} · {record['report_key']}",telegram_message_id=mid,metadata={'report_key':record['report_key'],'report_type':record['report_type']})
            except Exception:pass
        return {'sent':True,'message_id':mid,'outbox_id':item['id']}
    except Exception as exc:
        ambiguous=bool(getattr(exc,'ambiguous',False))
        retryable=bool(getattr(exc,'retryable',True))
        status=mark_outbox_failed(item['id'],str(exc),max_attempts=5 if retryable else 1,ambiguous=ambiguous)
        if item.get('signal_id') and item.get('operation_type')=='TELEGRAM_SIGNAL':
            update_signal(item['signal_id'],publication_status=status,telegram_error=str(exc))
        return {'sent':False,'status':status,'error':str(exc),'ambiguous':ambiguous,'outbox_id':item['id']}


def deliver_due(limit=20,**kwargs):
    return [deliver_item(item,**kwargs) for item in due_outbox(limit)]


def startup_recovery():
    return recover_interrupted_outbox()
