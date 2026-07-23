import asyncio
from decimal import Decimal

from app.services import cache, reservations


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, _ttl, value):
        self.values[key] = value


def test_revenue_cache_is_isolated_by_tenant(monkeypatch):
    fake_redis = FakeRedis()
    calls = []

    async def fake_calculation(property_id, tenant_id):
        calls.append((property_id, tenant_id))
        return {
            "property_id": property_id,
            "tenant_id": tenant_id,
            "total": "10.00" if tenant_id == "tenant-a" else "20.00",
            "currency": "USD",
            "count": 1,
        }

    monkeypatch.setattr(cache, "redis_client", fake_redis)
    monkeypatch.setattr(
        reservations, "calculate_total_revenue", fake_calculation
    )

    async def exercise_cache():
        tenant_a = await cache.get_revenue_summary("prop-001", "tenant-a")
        tenant_b = await cache.get_revenue_summary("prop-001", "tenant-b")
        tenant_a_cached = await cache.get_revenue_summary(
            "prop-001", "tenant-a"
        )
        return tenant_a, tenant_b, tenant_a_cached

    tenant_a, tenant_b, tenant_a_cached = asyncio.run(exercise_cache())

    assert tenant_a["total"] == "10.00"
    assert tenant_b["total"] == "20.00"
    assert tenant_a_cached == tenant_a
    assert calls == [
        ("prop-001", "tenant-a"),
        ("prop-001", "tenant-b"),
    ]
    assert set(fake_redis.values) == {
        "revenue:tenant-a:prop-001",
        "revenue:tenant-b:prop-001",
    }


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


class FakeSession:
    def __init__(self):
        self.calls = []

    async def execute(self, statement, params):
        self.calls.append((str(statement), params))
        if len(self.calls) == 1:
            return FakeResult("Europe/Paris")
        return FakeResult(Decimal("1000.000"))


def test_monthly_revenue_uses_tenant_and_property_local_boundaries():
    session = FakeSession()

    total = asyncio.run(
        reservations.calculate_monthly_revenue(
            "prop-001",
            3,
            2024,
            session,
            tenant_id="tenant-a",
        )
    )

    assert total == Decimal("1000.00")
    timezone_params = session.calls[0][1]
    revenue_params = session.calls[1][1]
    assert timezone_params == {
        "property_id": "prop-001",
        "tenant_id": "tenant-a",
    }
    assert revenue_params["tenant_id"] == "tenant-a"
    assert revenue_params["start_date"].isoformat() == "2024-03-01T00:00:00+01:00"
    assert revenue_params["end_date"].isoformat() == "2024-04-01T00:00:00+02:00"


def test_money_rounds_half_up_at_report_boundary():
    assert reservations._money("10.005") == Decimal("10.01")
    assert reservations._money("10.004") == Decimal("10.00")
