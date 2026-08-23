import asyncio
import httpx
import time
import sys
import json

async def run_tests():
    print("--- STARTING E2E VERIFICATION ---")

    # 1. Successful /search returning all records
    print("\n1. Fetching all records (empty query) to verify pagination and deduplication...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get("http://127.0.0.1:8000/search")
        data = r.json()
        
        resident_sources = data["sources"]["resident_index"]
        print(f"Resident Index Status: {resident_sources['status']}")
        print(f"Resident Total Fetched: {resident_sources['records_fetched']}")
        print(f"Resident Duplicates Removed: {resident_sources['duplicates_removed']}")
        
        # Verify 620 unique, 41 duplicates
        assert resident_sources['records_fetched'] == 661
        assert resident_sources['duplicates_removed'] == 41
        assert len(data["data"]["resident_index_matches"]) == 620
        
        benefits_sources = data["sources"]["benefits_register"]
        print(f"Benefits Register Status: {benefits_sources['status']}")
        print(f"Benefits Total Fetched: {benefits_sources['records_fetched']}")
        print(f"Benefits Attempts: {benefits_sources['attempts']}")
        
        if benefits_sources['status'] == 'ok':
            assert len(data["data"]["benefits_register_matches"]) == 540
            # Test PascalCase extraction
            sample = data["data"]["benefits_register_matches"][0]
            print(f"Sample Benefit: {sample}")
            assert sample['ref'] != ""
            assert sample['name'] != ""
        else:
            print(f"Benefits Failed (graceful degradation): {benefits_sources['error']}")
            assert len(data["data"]["benefits_register_matches"]) == 0

    # 2. Filtering
    print("\n2. Filtering for Delgado...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get("http://127.0.0.1:8000/search?last_name=Delgado")
        data = r.json()
        print(f"Resident Matches: {len(data['data']['resident_index_matches'])}")
        print(f"Benefit Matches: {len(data['data']['benefits_register_matches'])}")
        assert all("delgado" in x['last_name'].lower() for x in data['data']['resident_index_matches'])
        assert all("delgado" in x['name'].lower() for x in data['data']['benefits_register_matches'])
        
    # 3. Repeated identical requests
    print("\n3. Testing idempotency...")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r1 = await client.get("http://127.0.0.1:8000/search?last_name=Smith")
        r2 = await client.get("http://127.0.0.1:8000/search?last_name=Smith")
        # We can't strict equal JSON if sources attempts change, but the data block should be identical
        assert r1.json()["data"] == r2.json()["data"]
        print("Idempotency passed. Data is identical.")

    # 4. Stress test Day-2 40% failure
    print("\n4. Looping 10 times to test XML 40% failure recovery and/or graceful failure...")
    success_count = 0
    degraded_count = 0
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(10):
            r = await client.get("http://127.0.0.1:8000/search")
            s = r.json()["sources"]["benefits_register"]["status"]
            if s == "ok":
                success_count += 1
            else:
                degraded_count += 1
    print(f"Over 10 calls: {success_count} succeeded, {degraded_count} degraded.")

if __name__ == "__main__":
    asyncio.run(run_tests())
