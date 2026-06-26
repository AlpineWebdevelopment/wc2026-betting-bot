import { localOnly } from "@/lib/stub";

export const dynamic = "force-dynamic";

export async function GET() {
  return localOnly(
    "A szerver újraindítása nem értelmezett serverless környezetben (Vercel kezeli a folyamatokat)."
  );
}
