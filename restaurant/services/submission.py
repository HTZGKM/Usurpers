import hashlib
import json

from .common import ServiceError


def _fingerprint(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def replay(db, scope, actor, key, payload):
    if not key:
        return None
    row = db.execute("""SELECT fingerprint,result FROM mutation_requests
                        WHERE scope=? AND actor=? AND request_key=?""", (scope, actor, key)).fetchone()
    if row is None:
        return None
    if row["fingerprint"] != _fingerprint(payload):
        raise ServiceError("This submission was already used with different details.", 409,
                           code="IDEMPOTENCY_KEY_REUSED")
    return json.loads(row["result"])


def record(db, scope, actor, key, payload, result):
    if key:
        db.execute("""INSERT INTO mutation_requests(scope,actor,request_key,fingerprint,result)
                      VALUES(?,?,?,?,?)""", (scope, actor, key, _fingerprint(payload), json.dumps(result)))
    return result
