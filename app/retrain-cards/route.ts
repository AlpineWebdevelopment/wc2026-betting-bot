import { localOnly } from "@/lib/stub";

export const dynamic = "force-dynamic";

export async function GET() {
  return localOnly(
    "A kártya modell tanítása csak a helyi Python pipeline-ban fut. Futtasd a retrain_cards-t lokálisan, majd deployold az új card_model_params.json-nal."
  );
}
