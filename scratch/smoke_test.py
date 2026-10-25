import asyncio
from server.tools.repo_structure import get_repo_structure
from server.tools.readme_summary import summarize_readme
from server.tools.recent_commits import get_recent_commits
from server.tools.read_file import read_file
from server.tools.search_code import search_code


async def test_all():
    print("=== 1. get_repo_structure (psf/requests, root, depth=1) ===")
    r = await get_repo_structure("psf", "requests", path="", max_depth=1)
    if "error" in r:
        print("  ERROR:", r)
    else:
        print(f"  tree entries: {len(r['tree'])}, truncated: {r['truncated']}")
        for item in r["tree"][:5]:
            print(f"    {item['type']:5s}  {item['path']}")

    print()
    print("=== 2. summarize_readme (psf/requests) ===")
    r = await summarize_readme("psf", "requests")
    if "error" in r:
        print("  ERROR:", r)
    else:
        print(f"  README: {r['path']}, size: {r['size']} bytes")
        print(f"  First 200 chars: {repr(r['content'][:200])}")

    print()
    print("=== 3. get_recent_commits (psf/requests, limit=3) ===")
    r = await get_recent_commits("psf", "requests", limit=3)
    if "error" in r:
        print("  ERROR:", r)
    else:
        print(f"  count: {r['count']}")
        for c in r["commits"]:
            print(f"    {c['sha']}  {c['date'][:10]}  {c['message'][:60]}")

    print()
    print("=== 4. read_file (psf/requests, README.md) ===")
    r = await read_file("psf", "requests", "README.md", ref="main")
    if "error" in r:
        print(f"  ERROR/guardrail: {r.get('error')} - {r.get('message', r.get('suggestion', ''))}")
    else:
        print(f"  size: {r['size']} bytes, first 100 chars: {repr(r['content'][:100])}")

    print()
    print("=== 5. search_code (psf/requests, query=Session, ext=py) ===")
    r = await search_code("psf", "requests", "Session", file_extension="py")
    if "error" in r:
        print("  ERROR:", r)
    else:
        print(f"  total_count: {r['total_count']}, returned: {r['returned']}")
        for m in r["matches"][:3]:
            print(f"    {m['path']}")


asyncio.run(test_all())
