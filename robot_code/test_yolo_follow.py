"""YOLO tracking integration checks without a GPU or real robot."""

from collections import deque
from copy import deepcopy
from contextlib import nullcontext
import json
import sys
from types import SimpleNamespace

import numpy as np

from person_follow import PersonFollower, select_people, validate_tracking
from rgb_obstacles import Calibration
from vlm_reasoner import Reasoner


def rejected(call):
    try:
        call()
    except (TypeError, ValueError):
        return
    raise AssertionError('Malformed track IDs accepted')


def main():
    depth = np.full((100, 100), 2.)
    boxes = [[5, 10, 25, 90], [40, 10, 60, 90]]
    depth[10:90, 40:60] = 1.
    tracks = select_people(boxes, [.9, .3], [1, 1], depth, track_ids=[7, 8])
    assert [p['track_id'] for p in tracks['people']] == [8, 7], 'Range sorting changed ID association'
    assert len(select_people(boxes, [.9, .3], [1, 1], depth)['people']) == 1
    for ids in ([1], [True, False], [1.5, 2], [1, 1], [0, 2], [float('nan'), 2], [2**31, 2]):
        rejected(lambda: select_people(boxes, [.9, .9], [1, 1], depth, track_ids=ids))
    for bad in (True, -1, 0, '8', 2**31):
        changed = deepcopy(tracks); changed['people'][0]['track_id'] = bad
        rejected(lambda: validate_tracking(changed))
    changed = deepcopy(tracks); changed['people'][0]['kind'] = 'feet'
    rejected(lambda: validate_tracking(changed))

    follower = PersonFollower.__new__(PersonFollower)
    follower.reset_target()
    follower.locked_target = follower.lost_since = follower.last_seen_at = follower.last_target_box = None
    follower.range_samples = deque(maxlen=3)
    follower.gap, follower.search_direction = .5, 'left'
    selected = follower.select_target(tracks, 100.)
    assert selected['people'][selected['target']]['track_id'] == 8
    moved = deepcopy(tracks)
    moved['people'][0]['box'] = [.7, .1, .9, .9]
    moved['people'][1]['box'] = [.4, .1, .6, .9]
    selected = follower.select_target(moved, 100.1)
    assert selected['people'][selected['target']]['track_id'] == 8, 'A central bystander stole the target'
    assert follower.choose_direction(selected, 100.1)['direction'] == 'right'
    bystander = dict(people=[moved['people'][1]], target=0)
    absent = follower.select_target(bystander, 100.2)
    assert absent['target'] is None
    assert follower.choose_direction(absent, 100.2)['direction'] == 'stop'
    assert follower.select_target(bystander, 102.19)['target'] is None
    assert follower.select_target(bystander, 102.2)['target'] == 0, 'Loss timeout did not release the old ID'
    follower.locked_target = moved['people'][0]
    follower.selected_body_id = moved['people'][0]['track_id']
    follower.selected_body_seen_at = 102.9
    feet = dict(people=[dict(box=[.74,.8,.84,.95], range_m=1., score=.4, kind='feet')], target=0)
    assert follower.select_target(feet, 103.)['target'] == 0, 'Feet fallback lost the selected body'

    # Adapter must not return untracked/predicted boxes or swap RGB channels.
    seen = []; resets = []
    class Array:
        def __init__(self, a): self.a = np.asarray(a)
        def cpu(self): return self
        def numpy(self): return self.a
    class Boxes:
        is_track = True
        xyxy = Array([[40, 10, 60, 90]])
        conf = Array([.8])
        id = Array([5.])
        def __len__(self): return 1
    native_boxes = Boxes()
    def track(pixels, **kwargs):
        assert pixels[0,0].tolist() == [30,20,10] and kwargs['persist']
        assert kwargs['classes'] == [0]
        seen.append(True)
        return [SimpleNamespace(boxes=native_boxes)]
    follower.detector = SimpleNamespace(track=track, predictor=SimpleNamespace(
        trackers=[SimpleNamespace(reset=lambda: resets.append(True))]))
    follower.detector_seen_at = None
    rgb = np.full((100,100,3), [10,20,30], dtype=np.uint8)
    assert follower.detect_people(rgb, depth, 200.)['people'][0]['track_id'] == 5
    native_boxes.is_track = False
    assert follower.detect_people(rgb, depth, 200.1) == dict(people=[], target=None)
    native_boxes.is_track = True
    follower.detect_people(rgb, depth, 203.)
    assert len(resets) == 1 and follower.locked_target is None, 'Old IDs survived a disconnected stream'
    # Skip feet only when the already-selected body is observed this frame.
    follower.torch = SimpleNamespace(inference_mode=nullcontext)
    follower.guard = SimpleNamespace(calibration=Calibration(), estimate_depth=lambda _: depth)
    follower.steering_model = None
    follower.distance_scale = 1.
    follower.locked_target = tracks['people'][0]
    follower.selected_body_id = tracks['people'][0]['track_id']
    visible = dict(people=[tracks['people'][0]], target=0)
    feet_calls = []
    follower.detect_people = lambda *_: visible
    def fallback(*_):
        feet_calls.append(True)
        return dict(people=[], target=None)
    follower.detect_feet = fallback
    follower.decide(rgb, [])
    assert not feet_calls, 'A current selected body unnecessarily ran feet detection'
    visible = dict(people=[], target=None)
    follower.decide(rgb, [])
    assert len(feet_calls) == 1, 'Body loss did not immediately restore feet detection'
    visible = dict(people=[tracks['people'][1]], target=0)
    follower.decide(rgb, [])
    assert len(feet_calls) == 2, 'An unrelated bystander disabled feet fallback'
    worker = '''import json,sys
print(json.dumps({'ready':True,'metadata':{'name':'test','backend':'person_follow'}}),flush=True)
for n,line in enumerate(sys.stdin):
 json.loads(line)
 person={'box':[.4,.1,.6,.9],'range_m':1.,'score':.3,'track_id':8 if n==0 else True}
 print(json.dumps({'ok':True,'decision':{'direction':'straight','reason':'Test'},'latency_s':.01,'tracking':{'people':[person],'target':0}}),flush=True)
'''
    reasoner = Reasoner(None, None, command=[sys.executable, '-u', '-c', worker])
    rgb[:, :50] = 255
    try:
        decoded = reasoner.submit(rgb, []).result(timeout=3)
        assert decoded['tracking']['people'][0]['track_id'] == 8
        rejected(lambda: reasoner.submit(rgb, []).result(timeout=3))
    finally:
        reasoner.close()
    print('PASS: ID/range association, confidence and input validation, stable body target, loss wait, feet fallback, BGR input, current tracked boxes only, long-gap reset')


if __name__ == '__main__':
    main()
