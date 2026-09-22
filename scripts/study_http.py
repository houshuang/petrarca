"""Bounded mobile study routes and reversible suspension of legacy review."""
import os
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from curriculum_db import study_action

PAUSED_POST = {
 '/recall/select','/recall/grade','/resurfacing/select','/structural/grade','/review/answer',
 '/review/microlearning','/review/follow-up/trigger','/review/follow-up/generate',
 '/review/also-want-to-know','/review/batch-generate','/review/explore',
 '/curriculum/review/generate','/curriculum/review/result',
 '/curriculum/elicit/start','/curriculum/elicit/respond','/entity/questions',
 '/curriculum/knowledge/update','/curriculum/knowledge/import-assessment',
 '/review/voice-elicit','/review/elicit-know-nothing','/review/voice-memo',
 '/review/generate-question','/review/create-factual-quiz','/review/targeted-quiz',
 '/review/hamarquizen','/review/hamarquizen-cross','/knowledge/sweep/submit',
 '/knowledge/sweep/gaps','/defender/start','/defender/respond',
 '/book/resurfacing/respond','/explore/capture',
}


def route(handler, method):
    parsed = urlparse(handler.path)
    path = parsed.path
    if path.startswith('/study/'):
        try:
            if method == 'GET' and path in ('/study/status','/study/summary'):
                result = study_action(path.rsplit('/',1)[1])
            elif method == 'GET' and path == '/study/readings':
                result = study_action('readings')
            elif method == 'POST' and path == '/study/readings/select':
                body = handler._read_bounded_json_body(16*1024)
                if body is None:
                    return True
                result = study_action('readings-select', body)
            elif method == 'POST' and path in ('/study/session','/study/event'):
                body = handler._read_bounded_json_body(128*1024)
                if body is None:
                    return True
                result = study_action(path.rsplit('/',1)[1],body)
            elif method == 'POST' and path == '/study/voice':
                length = int(handler.headers.get('Content-Length','0'))
                if not 256 <= length <= 25*1024*1024:
                    raise ValueError('Audio must be between 256 bytes and 25 MB')
                q = parse_qs(parsed.query)
                data = handler.rfile.read(length)
                if len(data) != length:
                    raise ValueError('Incomplete audio upload; retry the saved recording')
                result = study_action('voice',run_id=q.get('run',[''])[0],item_id=q.get('item',[''])[0],
                         data=data,mime=handler.headers.get('Content-Type','audio/mp4'),
                         response_kind=q.get('kind',['recall'])[0], attempt_id=q.get('attempt',[None])[0],
                         audio_root=Path(os.environ.get('PETRARCA_DATA','/opt/petrarca/data'))/'audio/study')
            else:
                handler._send_private_json_response(404,{'error':'Unknown study route'})
                return True
            handler._send_private_json_response(200,result)
        except (ValueError,TypeError,KeyError) as exc:
            handler._send_private_json_response(400,{'error':str(exc)})
        except Exception as exc:
            print('[study] request failed:',type(exc).__name__,flush=True)
            handler._send_private_json_response(500,{'error':'Study request failed; your saved recording can be retried.'})
        return True
    if method=='POST' and path in PAUSED_POST and study_action('status')['active']:
        handler._send_private_json_response(409,{'error':'Other cards are suspended during the Norway study. Open Study in the updated phone app.'})
        return True
    if method=='GET' and path in ('/review/queue','/review/elicit-candidates') and study_action('status')['active']:
        handler._send_private_json_response(200,{'items':[],'candidates':[],'count':0,'study':study_action('status')})
        return True
    return False
