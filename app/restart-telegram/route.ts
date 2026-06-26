import { localOnly } from "@/lib/stub";

export const dynamic = "force-dynamic";

export async function GET() {
  return localOnly(
    "A Telegram bot külön, hosszan futó folyamat — nem futtatható serverless környezetben. Indítsd lokálisan a telegram_bot.py-t."
  );
}
