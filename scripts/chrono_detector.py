"""Read-only Chrono Rush recognition. No capture or input dependencies.

Calibrated on the supplied 2026-11-28 recording. All coordinates refer to
1280x720 BGR images; callers may pass any 16:9 game frame. The reward
card is located dynamically; the claim message must belong to that card.
"""
from dataclasses import dataclass
import cv2
import numpy as np

# Reference timestamps in seconds, boxes at 1280x720, mask type.
REFERENCES = {
    'card': (63, (485, 119, 568, 136), 'light'),
    'available': (63, (382, 221, 550, 241), 'yellow'),
    'event_title': (81, (82, 100, 442, 162), 'light'),
    'claim_label': (81, (130, 433, 314, 455), 'light'),
    'zero': (85, (202, 470, 263, 517), 'yellow'),
    'reward': (85, (610, 557, 671, 577), 'yellow'),
    'lobby_event': (77, (1081, 198, 1128, 232), 'light'),
    'blood_hunt': (89, (991, 539, 1098, 567), 'light'),
    'nightmare': (89, (1036, 446, 1105, 463), 'gray'),
    'start': (89, (1095, 583, 1157, 609), 'gray'),
}


def normalize(frame):
    if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
        raise ValueError('Expected uint8 BGR game frame')
    h, w = frame.shape[:2]
    if abs(w / h - 16 / 9) > .02:
        raise ValueError('Expected approximately 16:9 game frame')
    return cv2.resize(frame, (1280, 720), interpolation=cv2.INTER_AREA)


def mask(image, kind):
    if kind == 'gray':
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, s, v = cv2.split(cv2.cvtColor(image, cv2.COLOR_BGR2HSV))
    yellow = (h >= 15) & (h <= 40)
    if kind == 'yellow':
        hit = yellow & (s >= 70) & (v >= 135)
    else:
        hit = (v >= 175) & ((s <= 90) | yellow)
    return hit.astype(np.uint8) * 255


def find(image, template, box, kind):
    x, y, x2, y2 = box
    patch = mask(image[y:y2, x:x2], kind)
    if any(a < b for a, b in zip(patch.shape, template.shape)):
        return -1., (x, y)
    scores = cv2.matchTemplate(patch, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, (i, j) = cv2.minMaxLoc(scores)
    return float(score), (x + i, y + j)


@dataclass(frozen=True)
class Observation:
    card: str
    event: str
    lobby: bool
    reward_popup: bool
    scores: dict


class ChronoDetector:
    def __init__(self, templates):
        if set(templates) != set(REFERENCES):
            raise ValueError('Incomplete Chrono Rush references')
        self.templates = {}
        for name, (_, (x, y, x2, y2), kind) in REFERENCES.items():
            a = templates[name]
            if (a.dtype != np.uint8 or a.shape != (y2-y, x2-x)
                    or float(a.std()) < 8
                    or (kind != "gray" and not np.all((a == 0) | (a == 255)))):
                raise ValueError(f'Invalid template: {name}')
            self.templates[name] = a.copy()

    @classmethod
    def load(cls, path):
        with np.load(path, allow_pickle=False) as data:
            return cls({name: data[name] for name in data.files})

    @classmethod
    def from_frames(cls, frames):
        images = {t: normalize(frames[t]) for t in {v[0] for v in REFERENCES.values()}}
        return cls({name: mask(images[t][y:y2, x:x2], kind)
                    for name, (t, (x, y, x2, y2), kind) in REFERENCES.items()})

    def classify(self, frame):
        image = normalize(frame)
        scores = {}
        def search(name, box):
            score, point = find(image, self.templates[name], box, REFERENCES[name][2])
            scores[name] = score
            return score, point
        def fixed(name, margin=4):
            _, (x, y, x2, y2), _ = REFERENCES[name]
            return search(name, (x-margin, y-margin, x2+margin, y2+margin))[0]
        card = 'absent'
        heading, (x, y) = search('card', (150, 90, 1130, 165))
        if heading >= .80:
            claim, _ = search('available', (max(0, x-115), y+90, min(1280, x+90), y+135))
            card = 'available' if claim >= .80 else 'not_confirmed'
        event = 'absent'
        popup = False
        if fixed('event_title') >= .80 and fixed('claim_label') >= .80:
            zero = fixed('zero') >= .80
            h, s, v = cv2.split(cv2.cvtColor(image[556:586, 90:350], cv2.COLOR_BGR2HSV))
            bright = float(np.mean((h >= 15) & (h <= 40) & (s >= 130) & (v >= 245)))
            scores['claim_bright'] = bright
            popup = fixed('reward') >= .80
            if zero and bright < .10:
                event = 'empty'
            elif not zero and bright > .60:
                event = 'claim_candidate'
            else:
                event = 'uncertain'
        lobby = (fixed('lobby_event') >= .80 and fixed('blood_hunt') >= .80
                 and fixed('nightmare') >= .80 and fixed('start') >= .80)
        return Observation(card, event, lobby, popup, scores)
