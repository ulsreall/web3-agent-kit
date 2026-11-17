"""PoC — POST /swap/execute end to end.

    python3 poc_api.py

1. gate unconfigured -> fail-closed with an explicit message
2. WEB3_AUTO_AUTHORIZE=true -> the route reaches the signer
"""

import os

os.environ.setdefault("WEB3_API_KEY", "test-key")
os.environ.setdefault("PRIVATE_KEY", "0x" + "11" * 32)

from fastapi.testclient import TestClient  # noqa: E402

from web3_agent_kit.api import app  # noqa: E402

client = TestClient(app, headers={"X-API-Key": "test-key"})

print("1. no authorization provider configured:")
r = client.post("/swap/execute", params={"chain": "base"})
print("  ", r.status_code, r.text[:150])

print("\n2. WEB3_AUTO_AUTHORIZE=true:")
os.environ["WEB3_AUTO_AUTHORIZE"] = "true"
r = client.post("/swap/execute", params={"chain": "base", "amount_in": "0.001"})
print("  ", r.status_code, r.text[:150])

print("\n3. unknown token is rejected before any network call:")
r = client.post("/swap/execute", params={"chain": "base", "token_out": "NOTACOIN"})
print("  ", r.status_code, r.text[:150])
