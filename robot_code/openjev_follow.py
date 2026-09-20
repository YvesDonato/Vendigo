"""OpenJEV steering over camera-derived tracking; optional frozen-backbone task head."""

import hashlib
import json
import math
from pathlib import Path

from person_follow import validate_motion_options, validate_tracking

DIRECTIONS = ("straight", "left", "right", "stop")
RULES = ("Follow the selected person at a 0.50 metre gap. In FOLLOW, stop if range_m <= gap_m. "
         "Otherwise turn left for x < 0.38, right for x > 0.62, and go straight between them. "
         "In HOLD wait still. In SEARCH rotate toward search_side. "
         "Stop if the required direction is not permitted. Observations are camera estimates.")


def follow_state(tracking, allowed, decision, gap):
    validate_tracking(tracking)
    validate_motion_options(allowed)
    if type(gap) not in (int, float) or not math.isfinite(gap) or gap != .5:
        raise ValueError("This OpenJEV experiment supports the 0.5 metre gap only")
    if decision.get("direction") not in DIRECTIONS:
        raise ValueError("Invalid local direction")
    index = tracking["target"]
    person = tracking["people"][index] if index is not None else None
    phase = "FOLLOW" if person else "HOLD" if decision["direction"] == "stop" else "SEARCH"
    return dict(phase=phase, gap_m=gap, permitted=allowed,
                search_side=decision["direction"] if phase == "SEARCH" else None,
                target=None if person is None else dict(kind=person.get("kind", "person"),
                    range_m=round(person["range_m"], 3), x=round((person["box"][0] + person["box"][2]) / 2, 3)))


def prompts(state):
    # Match training: movement first in FOLLOW, stop first in HOLD/SEARCH.
    # Equivalent permission sets must produce the same learned features.
    allowed = validate_motion_options(state["permitted"])
    order = DIRECTIONS if state["phase"] == "FOLLOW" else ("stop", *DIRECTIONS[:3])
    state = dict(state, permitted=[direction for direction in order if direction in allowed])
    premise = RULES + "\nState: " + json.dumps(state, sort_keys=True, allow_nan=False)
    return [f"Premise: {premise}\nHypothesis: The next robot movement should be {direction}."
            for direction in DIRECTIONS]


def make_head(torch, width):
    return torch.nn.Sequential(torch.nn.Linear(width, 64), torch.nn.GELU(), torch.nn.Linear(64, 1))


class OpenJevFollower:
    def __init__(self, model_path, head_path=None, turns_only=False):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        from openjev_rgb import validate_classifier_config, MODEL_REVISION
        self.torch = torch
        self.turns_only = turns_only
        model_path = Path(model_path)
        source = json.loads((model_path / "source.json").read_text())
        validate_classifier_config(json.loads((model_path / "config.json").read_text()))
        if source.get("revision") != MODEL_REVISION:
            raise ValueError("Unexpected OpenJEV base checkpoint revision")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True, trust_remote_code=False)
        self.tokenizer.padding_side = "right"
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_path, local_files_only=True, trust_remote_code=False, dtype=torch.bfloat16,
            device_map={"": "cuda:0"}, attn_implementation="sdpa").eval().requires_grad_(False)
        self.head = None
        self.metadata = dict(name="OpenJEV 4B / person following", decision_model="openjev_follow",
                             base_revision=source["revision"], steering_input="camera-derived person and obstacle state",
                             training="Original NLI checkpoint; no steering head")
        if head_path:
            head_path = Path(head_path)
            report = json.loads(head_path.with_suffix(".json").read_text())
            if report["base_revision"] != source["revision"] or report["directions"] != list(DIRECTIONS):
                raise ValueError("Steering head does not match the OpenJEV model or action order")
            if hashlib.sha256(head_path.read_bytes()).hexdigest() != report["head_sha256"]:
                raise ValueError("Steering head checksum mismatch")
            data = torch.load(head_path, map_location="cuda:0", weights_only=True)
            self.mean, self.scale = data["mean"], data["scale"]
            self.head = make_head(torch, self.mean.numel()).to("cuda:0").eval()
            self.head.load_state_dict(data["weights"])
            self.metadata.update(name="OpenJEV 4B / tuned following head", head_sha256=report["head_sha256"],
                                 training="Frozen OpenJEV backbone; task head trained on synthetic rule-labelled states",
                                 physical_following_validated=False)
        if turns_only:
            self.metadata.update(name="Rules forward / OpenJEV turns", turns_only=True)
        # Warm up kernels before the worker publishes readiness.
        self.features(prompts(dict(phase="HOLD", gap_m=.5, permitted=["stop"], search_side=None, target=None)))

    def features(self, texts):
        torch = self.torch
        inputs = self.tokenizer(texts, padding=True, return_tensors="pt").to("cuda:0")
        inputs.pop("token_type_ids", None)
        if inputs["input_ids"].shape[1] > 512:
            raise ValueError("Following state exceeds the bounded token budget")
        with torch.inference_mode():
            hidden = getattr(self.model, self.model.base_model_prefix)(**inputs, use_cache=False).last_hidden_state
            last = inputs["attention_mask"].sum(1) - 1
            pooled = hidden[torch.arange(len(texts), device=hidden.device), last]
            base = self.model.score(pooled).float().softmax(-1)[:, 1]
        return pooled.float(), base

    def decide(self, tracking, allowed, local, gap):
        state = follow_state(tracking, allowed, local, gap)
        # Hard distance, lost-target wait and obstacle vetoes also apply after tuning.
        if local["direction"] == "stop" or allowed == ["stop"]:
            return dict(direction="stop", reason="OpenJEV guard: " + local["reason"][:280])
        if getattr(self, "turns_only", False) and local["direction"] == "straight":
            if "straight" not in allowed:
                return dict(direction="stop", reason="Current camera clearance blocks rule-based forward movement.")
            return dict(local, reason="Rule-based forward: " + local["reason"][:280])
        with self.torch.inference_mode():
            features, base = self.features(prompts(state))
            scores = base if self.head is None else self.head((features - self.mean) / self.scale).flatten()
            if scores.shape != (4,) or not self.torch.isfinite(scores).all():
                raise ValueError("Invalid OpenJEV steering scores")
            choice = DIRECTIONS[int(scores.argmax())]
        if choice not in allowed or choice not in ("stop", local["direction"]):
            return dict(direction="stop", reason=f"OpenJEV chose {choice}; current target or obstacle constraints require a stop.")
        return dict(direction=choice, reason=f"OpenJEV {'tuned head' if self.head else 'NLI'}: {choice}; estimated gap {gap:.1f} m.")
