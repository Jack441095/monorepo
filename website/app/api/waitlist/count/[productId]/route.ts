import type { NextRequest } from "next/server";
import { getDb } from "@/lib/db";

const CAPACITY: Record<string, number> = {
  "smart-sample-manager": 50,
  "submit": 50,
  "kenn": 50,
};

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ productId: string }> },
) {
  const { productId } = await params;
  const sql = getDb();

  const products = await sql`SELECT id FROM products WHERE id = ${productId}`;
  if (products.length === 0) {
    return Response.json({ detail: "Product not found" }, { status: 404 });
  }

  const capacity = CAPACITY[productId] ?? 50;
  const [{ count }] = await sql`
    SELECT count(*)::int AS count FROM waitlist_entries WHERE product_id = ${productId}
  `;

  return Response.json({ count, capacity });
}
