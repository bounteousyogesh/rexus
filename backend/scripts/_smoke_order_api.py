"""One-off: list order numbers present in local DB for manual testing."""
import asyncio
import os
import re
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
for line in (ROOT / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


async def main() -> None:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        has_col = await conn.fetchval(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.columns
              WHERE table_name = 'rexus_incidents_v3' AND column_name = 'u_order_number'
            )
            """
        )
        if has_col:
            rows = await conn.fetch(
                """
                SELECT u_order_number, COUNT(*)::int AS cnt
                FROM rexus_incidents_v3
                WHERE u_order_number IS NOT NULL AND TRIM(u_order_number) != ''
                GROUP BY u_order_number
                ORDER BY cnt DESC, u_order_number
                LIMIT 10
                """
            )
            print("BY u_order_number:")
            for r in rows:
                print(f"  {r['u_order_number']} ({r['cnt']} incident(s))")

        rows2 = await conn.fetch(
            """
            SELECT incident_number, short_description, description, work_notes, state
            FROM rexus_incidents_v3
            ORDER BY opened_at DESC NULLS LAST
            LIMIT 500
            """
        )
        seen: set[str] = set()
        print("\nFrom short_description / description / work_notes:")
        for r in rows2:
            blob = " ".join(
                filter(
                    None,
                    [r["short_description"], r["description"], r["work_notes"] or ""],
                )
            )
            for n in re.findall(r"\b\d{8,12}\b", blob):
                if n not in seen:
                    seen.add(n)
                    print(f"  {n}  (e.g. {r['incident_number']}, {r['state']})")
                if len(seen) >= 10:
                    break
            if len(seen) >= 10:
                break
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
