import { localOnly } from "@/lib/stub";

export const dynamic = "force-dynamic";

export async function GET() {
  return localOnly(
    "A modell tanítása csak a helyi Python pipeline-ban fut (scipy). Futtasd a retrain.py-t lokálisan, majd deployold az új model_params.json-nal."
  );
}
