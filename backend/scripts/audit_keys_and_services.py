import asyncio
import os
import sys
import time
import httpx
from dotenv import load_dotenv

# Ensure backend root is on sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

load_dotenv(os.path.join(backend_dir, ".env"))
from app.config import settings

def print_result(service: str, status: bool, detail: str, duration_ms: float = None):
    badge = "[PASS]" if status else "[FAIL]"
    timing = f" ({duration_ms:.1f}ms)" if duration_ms is not None else ""
    print(f"{badge} {service:<24} : {detail}{timing}")

async def test_mongodb():
    start = time.time()
    try:
        from pymongo import MongoClient
        client = MongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000)
        dbs = client.list_database_names()
        ms = (time.time() - start) * 1000
        print_result("MongoDB Atlas", True, f"Connected! Databases: {dbs[:4]} (total {len(dbs)})", ms)
        return True
    except Exception as e:
        ms = (time.time() - start) * 1000
        print_result("MongoDB Atlas", False, f"Error: {e}", ms)
        return False

async def test_clerk():
    start = time.time()
    key = settings.clerk_secret_key
    if not key:
        print_result("Clerk Secret Key", False, "No CLERK_SECRET_KEY set in .env")
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(
                "https://api.clerk.com/v1/users?limit=1",
                headers={"Authorization": f"Bearer {key}"}
            )
            ms = (time.time() - start) * 1000
            if res.status_code == 200:
                print_result("Clerk Secret Key", True, f"Valid! HTTP {res.status_code}", ms)
                return True
            else:
                print_result("Clerk Secret Key", False, f"HTTP {res.status_code}: {res.text[:80]}", ms)
                return False
    except Exception as e:
        ms = (time.time() - start) * 1000
        print_result("Clerk Secret Key", False, f"Exception: {e}", ms)
        return False

async def test_gemini():
    start = time.time()
    key = settings.gemini_api_key
    if not key:
        print_result("Google Gemini", False, "No GEMINI_API_KEY set in .env")
        return False
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.gemini_model}:generateContent?key={key}"
        payload = {
            "contents": [{"parts": [{"text": "Say 'OK' in one word."}]}],
            "generationConfig": {"maxOutputTokens": 10, "temperature": 0.1}
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(url, json=payload)
            ms = (time.time() - start) * 1000
            if res.status_code == 200:
                data = res.json()
                text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                print_result("Google Gemini", True, f"Model '{settings.gemini_model}' responded: '{text}'", ms)
                return True
            else:
                print_result("Google Gemini", False, f"HTTP {res.status_code}: {res.text[:120]}", ms)
                return False
    except Exception as e:
        ms = (time.time() - start) * 1000
        print_result("Google Gemini", False, f"Exception: {e}", ms)
        return False

async def test_groq():
    start = time.time()
    key = settings.groq_api_key
    if not key:
        print_result("Groq Cloud", False, "No GROQ_API_KEY set in .env")
        return False
    try:
        url = "https://api.groq.com/openai/v1/chat/completions"
        payload = {
            "model": settings.groq_model,
            "messages": [{"role": "user", "content": "Say 'OK'"}],
            "max_tokens": 10,
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                url,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload
            )
            ms = (time.time() - start) * 1000
            if res.status_code == 200:
                data = res.json()
                text = data["choices"][0]["message"]["content"].strip()
                print_result("Groq Cloud", True, f"Model '{settings.groq_model}' responded: '{text}'", ms)
                return True
            else:
                print_result("Groq Cloud", False, f"HTTP {res.status_code}: {res.text[:120]}", ms)
                return False
    except Exception as e:
        ms = (time.time() - start) * 1000
        print_result("Groq Cloud", False, f"Exception: {e}", ms)
        return False

async def test_ollama():
    start = time.time()
    host = settings.ollama_host
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            res = await client.get(f"{host}/api/tags")
            ms = (time.time() - start) * 1000
            if res.status_code == 200:
                models = [m.get("name") for m in res.json().get("models", [])]
                has_model = settings.ollama_model in models if settings.ollama_model else False
                print_result("Ollama Local", True, f"Server running. Installed models: {len(models)}. Active model available: {has_model}", ms)
                return True
            else:
                print_result("Ollama Local", False, f"HTTP {res.status_code}", ms)
                return False
    except Exception as e:
        ms = (time.time() - start) * 1000
        print_result("Ollama Local", False, f"Not reachable at {host} ({type(e).__name__})", ms)
        return False

async def test_openweather():
    start = time.time()
    key = settings.openweather_api_key
    if not key:
        print_result("OpenWeather API", False, "No OPENWEATHER_API_KEY set in .env")
        return False
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?lat={settings.location_lat}&lon={settings.location_lng}&appid={key}&units=metric"
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(url)
            ms = (time.time() - start) * 1000
            if res.status_code == 200:
                d = res.json()
                temp = d.get("main", {}).get("temp")
                cond = d.get("weather", [{}])[0].get("description", "")
                print_result("OpenWeather API", True, f"Valid! {settings.location_name}: {temp}°C, {cond}", ms)
                return True
            else:
                print_result("OpenWeather API", False, f"HTTP {res.status_code}: {res.text[:100]}", ms)
                return False
    except Exception as e:
        ms = (time.time() - start) * 1000
        print_result("OpenWeather API", False, f"Exception: {e}", ms)
        return False

async def test_tomtom():
    start = time.time()
    key = settings.tomtom_api_key
    if not key:
        print_result("TomTom Maps API", False, "No TOMTOM_API_KEY set in .env")
        return False
    try:
        url = f"https://api.tomtom.com/search/2/poiSearch/hospital.json?key={key}&lat={settings.location_lat}&lon={settings.location_lng}&radius=5000&limit=1"
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(url)
            ms = (time.time() - start) * 1000
            if res.status_code == 200:
                d = res.json()
                results_count = len(d.get("results", []))
                print_result("TomTom Maps API", True, f"Valid! Found {results_count} facility nearby", ms)
                return True
            else:
                print_result("TomTom Maps API", False, f"HTTP {res.status_code}: {res.text[:100]}", ms)
                return False
    except Exception as e:
        ms = (time.time() - start) * 1000
        print_result("TomTom Maps API", False, f"Exception: {e}", ms)
        return False

async def test_pinecone():
    start = time.time()
    key = settings.pinecone_api_key
    if not key:
        print_result("Pinecone Vector Store", False, "No PINECONE_API_KEY set in .env")
        return False
    try:
        from pinecone import Pinecone
        pc = Pinecone(api_key=key)
        indexes = pc.list_indexes()
        idx_names = [idx.name for idx in indexes]
        ms = (time.time() - start) * 1000
        target = (settings.pinecone_index or "default").lower()
        exists = any(name.lower() == target for name in idx_names)
        print_result("Pinecone Vector Store", True, f"Valid! Indexes: {idx_names}. Target '{target}' exists: {exists}", ms)
        return True
    except Exception as e:
        ms = (time.time() - start) * 1000
        print_result("Pinecone Vector Store", False, f"Exception: {e}", ms)
        return False

async def test_supermemory():
    start = time.time()
    key = settings.supermemory_api_key
    if not key:
        print_result("Supermemory API", False, "No SUPERMEMORY_API_KEY set in .env")
        return False
    try:
        url = "https://api.supermemory.ai/v4/memories"
        payload = {
            "memories": [{"content": "Audit ping", "metadata": {"type": "audit"}}],
            "containerTag": "medsys-audit-test"
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            res = await client.post(url, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=payload)
            ms = (time.time() - start) * 1000
            if res.status_code in (200, 201):
                doc_id = res.json().get("documentId", "ok")
                print_result("Supermemory API", True, f"Valid! HTTP {res.status_code} (Document ID: {doc_id})", ms)
                return True
            else:
                print_result("Supermemory API", False, f"HTTP {res.status_code}: {res.text[:100]}", ms)
                return False
    except Exception as e:
        ms = (time.time() - start) * 1000
        print_result("Supermemory API", False, f"Exception: {e}", ms)
        return False

async def test_firecrawl():
    start = time.time()
    key = settings.firecrawl_api_key
    if not key:
        print_result("Firecrawl API", False, "No FIRECRAWL_API_KEY set in .env")
        return False
    try:
        # Check credit / scrape endpoint with auth test
        url = "https://api.firecrawl.dev/v1/team/credit-usage"
        async with httpx.AsyncClient(timeout=6.0) as client:
            res = await client.get(url, headers={"Authorization": f"Bearer {key}"})
            ms = (time.time() - start) * 1000
            if res.status_code == 200:
                print_result("Firecrawl API", True, f"Valid! Credit usage: {res.json()}", ms)
                return True
            elif res.status_code == 404:
                # Check /v2 scrape or v1 status
                res_scrape = await client.post(
                    "https://api.firecrawl.dev/v2/scrape",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"url": "https://example.com", "formats": ["markdown"]}
                )
                if res_scrape.status_code in (200, 201):
                    print_result("Firecrawl API", True, f"Valid! Scrape succeeded", ms)
                    return True
                else:
                    print_result("Firecrawl API", False, f"HTTP {res_scrape.status_code}: {res_scrape.text[:100]}", ms)
                    return False
            else:
                print_result("Firecrawl API", False, f"HTTP {res_status.status_code}: {res.text[:100]}", ms)
                return False
    except Exception as e:
        ms = (time.time() - start) * 1000
        print_result("Firecrawl API", False, f"Exception: {e}", ms)
        return False

async def test_medgemma_adapter():
    start = time.time()
    url = settings.medgemma_adapter_url
    if not url:
        print_result("MedGemma Adapter URL", False, "Not set in .env (optional; falls back seamlessly to LLM)")
        return False
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # Ngrok requires an extra header or direct check
            res = await client.get(f"{url}/health", headers={"ngrok-skip-browser-warning": "true"})
            ms = (time.time() - start) * 1000
            if res.status_code == 200:
                print_result("MedGemma Adapter URL", True, f"Reachable: {url}", ms)
                return True
            else:
                print_result("MedGemma Adapter URL", False, f"HTTP {res.status_code} at {url} (system falls back to Gemini/Groq automatically)", ms)
                return False
    except Exception as e:
        ms = (time.time() - start) * 1000
        print_result("MedGemma Adapter URL", False, f"Unreachable: {url} ({type(e).__name__}) (system falls back to Gemini/Groq automatically)", ms)
        return False

async def test_backend_live_api():
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get("http://localhost:8000/health")
            ms = (time.time() - start) * 1000
            if res.status_code == 200:
                print_result("Live FastAPI Server", True, f"http://localhost:8000/health -> {res.text}", ms)
                return True
            else:
                print_result("Live FastAPI Server", False, f"HTTP {res.status_code}", ms)
                return False
    except Exception as e:
        ms = (time.time() - start) * 1000
        print_result("Live FastAPI Server", False, f"Not reachable: {e}", ms)
        return False

async def main():
    print("=" * 70)
    print("        MEDSYS AI: COMPREHENSIVE SERVICE & API KEY AUDIT       ")
    print("=" * 70)
    await test_backend_live_api()
    await test_mongodb()
    await test_clerk()
    await test_gemini()
    await test_groq()
    await test_ollama()
    await test_openweather()
    await test_tomtom()
    await test_pinecone()
    await test_supermemory()
    await test_firecrawl()
    await test_medgemma_adapter()
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())
