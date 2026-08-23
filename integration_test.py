import asyncio
import httpx
import sys

async def verify():
    # 1. Health check
    async with httpx.AsyncClient() as client:
        r = await client.get("http://127.0.0.1:8000/health")
        assert r.status_code == 200, f"Health failed: {r.status_code}"
        print("Health OK.")

    # 2. Residents check
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get("http://127.0.0.1:8000/residents")
        assert r.status_code == 200
        data = r.json()
        assert data["data"]["total"] == 620, f"Expected 620 unique residents, got {data['data']['total']}"
        assert data["sources"]["resident_index"]["status"] == "ok"
        print(f"Residents OK: fetched 620, duplicates removed {data['sources']['resident_index']['duplicates_removed']}")

    # 3. Benefits check (Day-2 40% failure rate might cause some unavailability, but we should test it)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get("http://127.0.0.1:8000/benefits")
        assert r.status_code == 200
        data = r.json()
        status = data["sources"]["benefits_register"]["status"]
        if status == "ok":
            assert data["data"]["total"] == 540, "Expected 540 benefits on success"
            print("Benefits OK: successfully fetched and parsed XML.")
        else:
            print(f"Benefits DEGRADED (as expected occasionally with 40% failure): {data['sources']['benefits_register']['error']}")

if __name__ == "__main__":
    asyncio.run(verify())
