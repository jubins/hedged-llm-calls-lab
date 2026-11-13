import random

import httpx
import pytest

from upstream import server


def test_upstream_sample_has_a_long_tail():
    rng = random.Random(7)
    samples = sorted(server.sample_ms(rng) for _ in range(20000))
    p50, p99 = samples[10000], samples[int(0.99 * 20000)]
    assert 90 < p50 < 160
    assert p99 > 1000


@pytest.mark.asyncio
async def test_gateway_modes(monkeypatch):
    from gateway import app as gw

    async def fake_post(url):
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(gw.client, "post", fake_post)
    transport = httpx.ASGITransport(app=gw.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        for mode in ("plain", "timeout", "hedged"):
            r = await c.post("/ask", params={"mode": mode})
            assert r.status_code == 200 and r.json()["mode"] == mode
        assert (await c.post("/ask", params={"mode": "nope"})).status_code == 422
        assert b"call_seconds_bucket" in (await c.get("/metrics")).content
