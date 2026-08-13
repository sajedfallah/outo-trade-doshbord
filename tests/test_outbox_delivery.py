from storage import repo
from telegram.outbox import deliver_item
from telegram.publisher import TelegramDeliveryError
from tests.conftest import signal


def ok_message(*args,**kwargs):return {'result':{'message_id':77}}


def test_signal_delivery_updates_signal(repo_db):
    created=repo.create_signal_durable(signal(),outbox_payload={'text':'signal'})
    result=deliver_item(created['outbox'],send_message_fn=ok_message)
    saved=repo.get_signal('NX-001')
    assert result['sent'] and saved['telegram_message_id']==77 and saved['publication_status']=='SENT'


def test_definite_telegram_failure_retries(repo_db):
    item=repo.enqueue_outbox('partial','TELEGRAM_PARTIAL',{'text':'partial'},'NX-001')
    def fail(*args,**kwargs):raise TelegramDeliveryError('rate limited',ambiguous=False)
    result=deliver_item(item,send_message_fn=fail)
    assert result['status']=='FAILED'


def test_ambiguous_telegram_failure_never_auto_duplicates(repo_db):
    item=repo.enqueue_outbox('final','TELEGRAM_FINAL',{'text':'final'},'NX-001')
    def timeout(*args,**kwargs):raise TelegramDeliveryError('timeout',ambiguous=True)
    result=deliver_item(item,send_message_fn=timeout)
    assert result['status']=='UNKNOWN'
    assert deliver_item(repo.get_outbox_item(item_id=item['id']),send_message_fn=ok_message)['reason']=='UNKNOWN'


def test_partial_event_retry_updates_message(repo_db):
    repo.insert_event({'event_key':'NX-001:PARTIAL:1','signal_id':'NX-001','event_type':'PARTIAL_CLOSE'})
    item=repo.enqueue_outbox('partial-event','TELEGRAM_PARTIAL',{'text':'p','event_key':'NX-001:PARTIAL:1'},'NX-001')
    assert deliver_item(item,send_message_fn=ok_message)['sent']
    assert repo.list_trade_events('NX-001')[0]['telegram_message_id']==77


def test_final_event_retry_updates_message(repo_db):
    repo.insert_event({'event_key':'NX-001:FINAL:1','signal_id':'NX-001','event_type':'FINAL_CLOSE'})
    item=repo.enqueue_outbox('final-event','TELEGRAM_FINAL',{'text':'f','event_key':'NX-001:FINAL:1'},'NX-001')
    assert deliver_item(item,send_message_fn=ok_message)['sent']
    assert repo.list_trade_events('NX-001')[0]['telegram_message_id']==77
