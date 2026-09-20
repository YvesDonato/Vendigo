"""Train a small head on frozen OpenJEV features. Synthetic policy imitation, not visual driving validation."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import time

from openjev_follow import DIRECTIONS, OpenJevFollower, make_head, prompts


def teacher(state):
    target = state["target"]
    if state["phase"] == "HOLD":
        choice = "stop"
    elif state["phase"] == "SEARCH":
        choice = state["search_side"]
    elif target["range_m"] <= state["gap_m"]:
        choice = "stop"
    else:
        choice = "left" if target["x"] < .38 else "right" if target["x"] > .62 else "straight"
    return choice if choice in state["permitted"] else "stop"


def dataset():
    rng = random.Random(20260919)
    splits, used = {}, set()
    for split, count in (("train", 480), ("validation", 120), ("test", 200)):
        rows = []
        while len(rows) < count:
            desired = DIRECTIONS[len(rows) % 4]
            state = dict(phase="FOLLOW", gap_m=.5, permitted=list(DIRECTIONS), search_side=None,
                         target=dict(kind=rng.choice(["feet", "person"]),
                                     range_m=round(rng.uniform(.3, 3.), 3), x=round(rng.uniform(.05, .95), 3)))
            if rng.random() < .2:
                state["permitted"].remove(rng.choice(DIRECTIONS[:3]))
            label = teacher(state)
            key = prompts(state)[0]
            if label == desired and key not in used:
                used.add(key)
                rows.append(dict(state=state, label=label))
        splits[split] = rows
    # Discrete loss/search states belong to training only; runtime guards test the wait separately.
    for phase, side in (("HOLD", None), ("SEARCH", "left"), ("SEARCH", "right")):
        state = dict(phase=phase, gap_m=.5, permitted=["stop"] if side is None else ["stop", side],
                     search_side=side, target=None)
        splits["train"].append(dict(state=state, label=teacher(state)))
    keys = [{prompts(row["state"])[0] for row in rows} for rows in splits.values()]
    assert all(not a.intersection(b) for i, a in enumerate(keys) for b in keys[i + 1:])
    return splits


def metrics(torch, scores, labels):
    prediction = scores.argmax(1)
    stop = DIRECTIONS.index("stop")
    moving, stopped = labels != stop, labels == stop
    return dict(accuracy=float((prediction == labels).float().mean()),
                unnecessary_stops=int(((prediction == stop) & moving).sum()), movement_cases=int(moving.sum()),
                missed_required_stops=int(((prediction != stop) & stopped).sum()), stop_cases=int(stopped.sum()),
                wrong_turns=int(((prediction != labels) & moving & (prediction != stop)).sum()),
                guarded_unnecessary_stops=int(((prediction != labels) & moving).sum()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import torch
    torch.manual_seed(19)
    torch.set_num_threads(4)
    args.output.mkdir(parents=True, exist_ok=True)
    splits = dataset()
    dataset_file = args.output / "dataset.json"
    dataset_file.write_text(json.dumps(splits, indent=2) + "\n")
    encoder = OpenJevFollower(args.model)
    features, bases, labels = {}, {}, {}
    for split, rows in splits.items():
        texts = [text for row in rows for text in prompts(row["state"])]
        chunks, baseline = [], []
        started = time.monotonic()
        for i in range(0, len(texts), 8):
            x, base = encoder.features(texts[i:i + 8])
            chunks.append(x.cpu())
            baseline.append(base.cpu())
            if i % 160 == 0:
                print(f"{split}: {i}/{len(texts)} pairs, {time.monotonic() - started:.1f}s", flush=True)
        features[split] = torch.cat(chunks).reshape(len(rows), 4, -1)
        bases[split] = torch.cat(baseline).reshape(len(rows), 4)
        labels[split] = torch.tensor([DIRECTIONS.index(row["label"]) for row in rows])
    torch.save(dict(features=features, bases=bases, labels=labels), args.output / "features.pt")
    mean = features["train"].flatten(0, 1).mean(0)
    scale = features["train"].flatten(0, 1).std(0).clamp_min(.01)
    features = {key: (x - mean) / scale for key, x in features.items()}
    head = make_head(torch, mean.numel())
    optimizer = torch.optim.AdamW(head.parameters(), lr=.001, weight_decay=.01)
    best, best_weights, selected_epoch = float("inf"), None, None
    for epoch in range(100):
        head.train()
        for indices in torch.randperm(len(labels["train"])).split(64):
            loss = torch.nn.functional.cross_entropy(head(features["train"][indices]).squeeze(-1), labels["train"][indices])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        head.eval()
        with torch.no_grad():
            validation = float(torch.nn.functional.cross_entropy(head(features["validation"]).squeeze(-1), labels["validation"]))
        if validation < best:
            best, selected_epoch = validation, epoch
            best_weights = {key: value.detach().clone() for key, value in head.state_dict().items()}
        if epoch - selected_epoch >= 12:
            break
    head.load_state_dict(best_weights)
    head_path = args.output / "head.pt"
    torch.save(dict(weights=best_weights, mean=mean, scale=scale), head_path)
    report = dict(base_revision=encoder.metadata["base_revision"], directions=list(DIRECTIONS),
                  head_sha256=hashlib.sha256(head_path.read_bytes()).hexdigest(),
                  dataset_sha256=hashlib.sha256(dataset_file.read_bytes()).hexdigest(),
                  trainable_parameters=sum(p.numel() for p in head.parameters()),
                  selected_epoch=selected_epoch, physical_following_validated=False,
                  method="Frozen OpenJEV 4B features; 64-unit steering head; synthetic rule imitation",
                  limitations="Disjoint exact states share templates and rules. No real-image labels or closed-loop driving evaluation.",
                  splits={key: dict(count=len(rows), labels=dict(Counter(row["label"] for row in rows))) for key, rows in splits.items()})
    with torch.no_grad():
        for split in ("validation", "test"):
            report[split] = dict(original=metrics(torch, bases[split], labels[split]),
                                 tuned=metrics(torch, head(features[split]).squeeze(-1), labels[split]))
    head_path.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    # Reload the exact saved artifact and measure single-state inference, including tokenization.
    del encoder
    torch.cuda.empty_cache()
    loaded = OpenJevFollower(args.model, head_path)
    times = []
    for row in splits["test"][:20]:
        started = time.monotonic()
        x, _ = loaded.features(prompts(row["state"]))
        with torch.inference_mode():
            actual = loaded.head((x - loaded.mean) / loaded.scale).flatten().cpu()
            expected = head(features["test"][len(times)]).flatten()
        assert torch.equal(actual.argmax(), expected.argmax()), "Export reload changed the selected action"
        times.append(time.monotonic() - started)
    report["reload_passed"] = True
    report["inference_ms_median"] = 1000 * sorted(times)[len(times)//2]
    report["inference_ms_max"] = 1000 * max(times)
    head_path.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
