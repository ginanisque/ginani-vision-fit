import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient
from app.capture import capture_decision
from app.main import app


def subject(cord=True, clipped=False, duplicate=False):
    image = np.full((600,400,3),180,np.uint8)
    y = 0 if clipped else 45
    image[y:555,120:280] = np.random.default_rng(12).integers(65,105,(555-y,160,1),dtype=np.uint8)
    if cord: image[290:298,120:280] = (30,220,30)
    if duplicate: image[260:268,120:280] = (30,220,30)
    return image


def encoded(image): return cv2.imencode('.png',image)[1].tobytes()


def test_candidate_requires_review():
    image = subject()
    r = capture_decision('front',image,encoded(image))
    assert r['decision'] == 'review'
    assert r['captureChecks']['waistCord']['status'] == 'candidate'
    assert r['captureChecks']['posture']['status'] == 'unknown'
    assert r['captureChecks']['framing']['status'] == 'pass'
    assert {e['kind'] for e in r['evidence']} == {'subject-candidate','cord-candidate'}


@pytest.mark.parametrize('options,status', [({'cord':False},'missing'),({'duplicate':True},'ambiguous')])
def test_cord_failure_changes_action(options,status):
    image = subject(**options)
    r = capture_decision('side',image,encoded(image))
    assert r['decision'] == 'recapture'
    assert r['captureChecks']['waistCord']['status'] == status


def test_clipped_framing():
    image = subject(clipped=True)
    r = capture_decision('front',image,encoded(image))
    assert r['decision'] == 'recapture'
    assert r['captureChecks']['framing']['status'] == 'fail'


def test_no_subject_never_proceeds():
    image = np.full((600,400,3),180,np.uint8)
    r = capture_decision('front',image,encoded(image))
    assert r['decision'] != 'proceed'
    assert not r['evidence']


def test_original_coordinates():
    image = cv2.resize(subject(),(1200,1800))
    r = capture_decision('front',image,encoded(image))
    assert 350 <= r['evidence'][0]['box']['x'] <= 370
    assert r['evidence'][0]['box']['width'] > 470


@pytest.mark.parametrize('endpoint',['/api/capture','/api/turn-video'])
def test_consent(endpoint):
    with TestClient(app) as c:
        assert c.post(endpoint,data={'view':'front'},files={'file':('photo.png',encoded(subject()))}).status_code == 403


def test_capture_is_recorded():
    with TestClient(app) as c:
        r = c.post('/api/capture',data={'view':'front','consent':'true'},files={'file':('photo.png',encoded(subject()))})
        assert r.status_code == 200
        assert r.json()['decision'] == 'review'
        assert c.get('/api/decisions').json()['records'][-1]['id'] == r.json()['id']


def test_bad_video():
    with TestClient(app) as c:
        assert c.post('/api/turn-video',data={'consent':'true'},files={'file':('bad.webm',b'bad')}).status_code == 400


@pytest.mark.parametrize('seconds,dark,decision',[(10,False,'review'),(2,True,'recapture')])
def test_video_quality_and_duration(tmp_path,seconds,dark,decision,monkeypatch):
    # Isolate duration/quality: disable the pose model so turn coverage stays
    # 'unknown' (coverage is tested separately in test_posture.py).
    import app.main as main_module
    monkeypatch.setattr(main_module, 'load_pose', lambda: None)
    monkeypatch.setattr(main_module, 'estimate_pose', lambda frame, pose=None: None)

    path = tmp_path/'turn.avi'
    writer = cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*'MJPG'),10,(400,600))
    assert writer.isOpened()
    for _ in range(seconds*10): writer.write(np.zeros((600,400,3),np.uint8) if dark else subject())
    writer.release()
    with TestClient(app) as c:
        r = c.post('/api/turn-video',data={'consent':'true'},files={'file':('turn.avi',path.read_bytes())})
        assert r.status_code == 200
        assert r.json()['durationSeconds'] == seconds
        assert len(r.json()['samples']) == 5
        assert r.json()['decision'] == decision


def test_longer_video_is_sampled_not_penalized_for_duration(tmp_path, monkeypatch):
    # A user should not need to time a slow turn precisely: a longer clip with good
    # frames is sampled across the whole turn and stays 'review' rather than being
    # rejected or marked 'recapture' for its length.
    import app.main as main_module
    monkeypatch.setattr(main_module, 'load_pose', lambda: None)
    monkeypatch.setattr(main_module, 'estimate_pose', lambda frame, pose=None: None)

    seconds = 30
    path = tmp_path/'turn.avi'
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*'MJPG'), 10, (400, 600))
    assert writer.isOpened()
    for _ in range(seconds * 10):
        writer.write(subject())
    writer.release()
    with TestClient(app) as c:
        r = c.post('/api/turn-video', data={'consent': 'true'}, files={'file': ('turn.avi', path.read_bytes())})
        assert r.status_code == 200
        assert r.json()['durationSeconds'] == seconds
        assert r.json()['decision'] == 'review'
