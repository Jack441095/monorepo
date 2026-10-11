"""Short-lived observations for exact bus/rack parameter reads and guarded writes."""

import hashlib
import json
import math
import time
import uuid

FEATURE = "device_parameter_target.v1"


class ParameterTargets:
    """Keep object references inside Live; exported tokens are observations, never host IDs."""

    def __init__(self, song):
        self.song = song
        self.epoch = uuid.uuid4().hex
        self.observations = {}

    def _resolve(self, address, parameter_index):
        if not isinstance(address, dict) or set(address) != {"kind", "index", "device_path"}:
            raise ValueError("Exact kind, index and device_path are required")
        kind, index, path = address["kind"], address["index"], address["device_path"]
        if type(index) is not int or index < 0 or kind not in ("track", "return", "master"):
            raise ValueError("Invalid bus position")
        if not isinstance(path, list) or not 1 <= len(path) <= 9 or len(path) % 2 != 1:
            raise ValueError("Invalid device/chain path")
        if any(type(item) is not int or item < 0 for item in path) or type(parameter_index) is not int or parameter_index < 0:
            raise ValueError("Indices must be non-negative integers")
        if kind == "master":
            if index != 0:
                raise ValueError("Master index must be zero")
            track = self.song.master_track
        else:
            track = (self.song.tracks if kind == "track" else self.song.return_tracks)[index]
        device = track.devices[path[0]]
        objects, labels = [track, device], [str(track.name), str(device.name)]
        for offset in range(1, len(path), 2):
            chain = device.chains[path[offset]]
            device = chain.devices[path[offset + 1]]
            objects.extend((chain, device))
            labels.extend((str(chain.name), str(device.name)))
        parameter = device.parameters[parameter_index]
        objects.append(parameter)
        return track, device, parameter, objects, labels

    def _topology(self, track):
        def node(device, depth):
            result = {"name": str(device.name), "class_name": str(getattr(device, "class_name", ""))}
            chains = getattr(device, "chains", ())
            if chains:
                if depth >= 4:
                    raise ValueError("Rack topology exceeds four nested chains")
                result["chains"] = [{"name": str(chain.name), "devices": [node(inner, depth + 1) for inner in chain.devices]} for chain in chains]
            return result
        payload = {"epoch": self.epoch, "track_name": str(track.name), "devices": [node(device, 0) for device in track.devices]}
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

    def _metadata(self, parameter, index):
        # LOM documents these flags, but Python builds may omit them. Unknown flags block this new writer.
        state = getattr(parameter, "state", None)
        rows = {
            "index": index, "name": str(parameter.name), "original_name": str(getattr(parameter, "original_name", parameter.name)),
            "value": float(parameter.value), "min": float(parameter.min), "max": float(parameter.max),
            "value_display": str(parameter.str_for_value(parameter.value)),
            "quantized": bool(parameter.is_quantized), "is_enabled": getattr(parameter, "is_enabled", None),
            "state": int(state) if state is not None else None,
            "automation_state": int(parameter.automation_state) if hasattr(parameter, "automation_state") else None,
            "value_items": list(getattr(parameter, "value_items", ())) if parameter.is_quantized else [],
            "macro_controlled": None,
        }
        # Labels alone do not establish raw positions, especially for third-party plug-ins.
        rows["choices"] = None
        return rows

    def read(self, address, parameter_index, reference=None):
        track, device, parameter, objects, labels = self._resolve(address, parameter_index)
        topology = self._topology(track)
        now = time.monotonic()
        self.observations = {token: row for token, row in self.observations.items() if row["expires"] > now}
        if reference:
            previous = self.observations.get(reference)
            if previous is None or len(objects) != len(previous["objects"]) or any(a is not b for a, b in zip(objects, previous["objects"])) or topology != previous["topology"]:
                raise ValueError("Observed objects or topology changed; inspect again")
        token = uuid.uuid4().hex
        # 256 observations and 300 seconds bound memory and match confirmation expiry.
        if len(self.observations) >= 256:
            self.observations.pop(next(iter(self.observations)))
        metadata = self._metadata(parameter, parameter_index)
        self.observations[token] = {"objects": objects, "topology": topology, "expires": now + 300, "used": False}
        return {"success": True, "target_address": address, "topology": topology, "observation_token": token,
                "device_name": str(device.name), "track_name": str(track.name), "target_label": " / ".join(labels + [str(parameter.name)]),
                "parameters": [metadata], "feature": FEATURE,
                "limitations": ["Observation tokens expire and do not survive Remote Script reload.",
                                "Chooser labels have no qualified raw positions.", "Macro assignments are unavailable; disabled controls are refused."]}

    def write(self, address, parameter_index, value, expected):
        reference = expected["observation_token"]
        fresh = self.read(address, parameter_index, reference)
        observation = self.observations[reference]
        if observation["used"]:
            raise ValueError("This observation already attempted a write; inspect state before retrying")
        parameter = fresh["parameters"][0]
        if fresh["topology"] != expected["topology"] or parameter != expected["parameters"][0]:
            raise ValueError("Parameter state changed before write")
        if isinstance(value, bool):
            raise ValueError("Boolean values are not raw parameter values")
        value = float(value)
        if not all(math.isfinite(item) for item in (value, parameter["value"], parameter["min"], parameter["max"])) or not parameter["min"] <= parameter["value"] <= parameter["max"] or not parameter["min"] <= value <= parameter["max"]:
            raise ValueError("Invalid raw value or range")
        if parameter["is_enabled"] is not True or parameter["state"] != 0 or parameter["automation_state"] != 0:
            raise ValueError("Enabled/state/automation metadata does not permit this write")
        if parameter["quantized"] and value not in {parameter["value"], parameter["min"], parameter["max"]}:
            # value_items supplies labels, not a measured mapping to intermediate raw positions.
            raise ValueError("Intermediate chooser values need a qualified raw option table")
        # Mark before the setter: an exception may have happened after Live accepted the value.
        observation["used"] = True
        _, _, live_parameter, _, _ = self._resolve(address, parameter_index)
        live_parameter.value = value
        return {"success": True, "sent": True, "verified": False}


def register_parameter_targets(server, song):
    """Register the versioned protocol with nonce echoes; every reply is attributable."""
    targets = ParameterTargets(song)
    def callback(operation, params):
        nonce = str(params[0])
        try:
            request = json.loads(params[1])
            if operation == "features":
                result = {"success": True, "features": [FEATURE], "epoch": targets.epoch}
            elif operation == "read":
                result = targets.read(request["address"], request["parameter_index"], request.get("reference"))
            else:
                result = targets.write(request["address"], request["parameter_index"], request["value"], request["expected"])
            encoded = json.dumps(result, allow_nan=False)
        except Exception as exc:
            # A setter exception is ambiguous; the client reconciles through a fresh read.
            result = {"success": False, "error": str(exc)}
            encoded = json.dumps(result, allow_nan=False)
        return (nonce, encoded)
    for operation in ("features", "read", "write"):
        server.add_handler("/live/kenn/parameter_target/" + operation, lambda params, op=operation: callback(op, params))
    return targets
