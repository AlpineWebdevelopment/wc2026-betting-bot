import { localOnly } from "@/lib/stub";

export const dynamic = "force-dynamic";

export async function GET() {
  return localOnly(
    "A sarok modell tanítása csak a helyi Python pipeline-ban fut. Futtasd a retrain_corners-t lokálisan, majd deployold az új corner_model_params.json-nal."
  );
}
