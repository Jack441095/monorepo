export type WaitlistJoin = {
  email: string;
  product_id: string;
  name: string | null;
  use_case: string | null;
};

export function parseWaitlistJoin(body: unknown): WaitlistJoin | null {
  if (!body || typeof body !== "object" || Array.isArray(body)) return null;
  const values = body as Record<string, unknown>;
  if (typeof values.email !== "string" || typeof values.product_id !== "string") return null;

  const email = values.email.trim().toLowerCase();
  const product_id = values.product_id.trim();
  if (email.length > 254 || !/^[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+$/.test(email)) return null;
  if (!/^[a-z0-9][a-z0-9-]{0,99}$/.test(product_id)) return null;

  // Bound the free-text fields before any database call; they come from a public form.
  const optionalText = (value: unknown, maxLength: number): string | null | undefined => {
    if (value === null || value === undefined) return null;
    if (typeof value !== "string" || value.length > maxLength) return undefined;
    return value.trim() || null;
  };
  const name = optionalText(values.name, 100);
  const use_case = optionalText(values.use_case, 1000);
  if (name === undefined || use_case === undefined) return null;
  return { email, product_id, name, use_case };
}
