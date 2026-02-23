import copy
import hashlib
import json
import time


def _serialize(obj):
    return json.dumps(obj, sort_keys=True, default=str).encode()


class ExecutionIntegrityCore:
    def __init__(self):
        self.chain = []
        self.previous_hash = "GENESIS"

    def record(self, action, input_data, output_data, ts=None):
        if ts is None:
            ts = time.time()

        entry = {
            "timestamp": ts,
            "action": copy.deepcopy(action),
            "input": copy.deepcopy(input_data),
            "output": copy.deepcopy(output_data),
            "previous_hash": self.previous_hash,
        }

        raw = _serialize(entry)
        current_hash = hashlib.sha256(raw).hexdigest()

        entry["hash"] = current_hash
        self.previous_hash = current_hash
        self.chain.append(entry)

    def export(self, filename="execution_log.json", exported_at=None):
        if exported_at is None:
            exported_at = time.time()

        envelope = {
            "spec": "execution-integrity-core",
            "version": "0.1.2",
            "exported_at": exported_at,
            "hash_alg": "sha256",
            "chain": self.chain,
        }

        with open(filename, "w") as f:
            json.dump(envelope, f, indent=2, sort_keys=True, default=str)

        return filename

    def verify(self):
        prev = "GENESIS"
        for entry in self.chain:
            try:
                temp = dict(entry)
                expected = temp.pop("hash")

                raw = _serialize(temp)
                recalculated = hashlib.sha256(raw).hexdigest()

                if recalculated != expected or entry.get("previous_hash") != prev:
                    return False
            except (KeyError, TypeError, ValueError):
                return False

            prev = expected

        return True
