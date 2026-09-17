import { getDb } from "@/lib/db";

const CAPACITY: Record<string, number> = {
  "smart-sample-manager": 50,
  "submit": 50,
  "kenn": 50,
};

export async function POST(request: Request) {
  const body = await request.json();
  const { email, name, product_id, use_case } = body;

  if (!email || !product_id) {
    return Response.json({ detail: "email and product_id are required" }, { status: 400 });
  }

  const sql = getDb();

  const products = await sql`SELECT id FROM products WHERE id = ${product_id}`;
  if (products.length === 0) {
    return Response.json({ detail: "Product not found" }, { status: 404 });
  }

  const capacity = CAPACITY[product_id] ?? 50;

  const existing = await sql`
    SELECT id FROM waitlist_entries
    WHERE email = ${email} AND product_id = ${product_id}
    LIMIT 1
  `;

  if (existing.length === 0) {
    await sql`
      INSERT INTO waitlist_entries (id, email, name, product_id, use_case, created_at)
      VALUES (gen_random_uuid(), ${email}, ${name ?? null}, ${product_id}, ${use_case ?? null}, now())
      ON CONFLICT (email, product_id) DO NOTHING
    `;
  }

  const [{ count }] = await sql`
    SELECT count(*)::int AS count FROM waitlist_entries WHERE product_id = ${product_id}
  `;

  return Response.json({ ok: true, count, capacity });
}
