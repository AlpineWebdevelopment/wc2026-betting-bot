"""
Run this locally to pre-train the model and save params.
Vercel loads the saved params — no training needed at request time.
"""
import json
import numpy as np
from data import fetch_data
from model import PoissonModel

print("Fetching data and training model...")
df = fetch_data()
model = PoissonModel().fit(df)

params = {
    "teams": model.teams,
    "params": model.params.tolist(),
    "avg_attack": model._avg_attack,
    "avg_defense": model._avg_defense,
}

with open("model_params.json", "w") as f:
    json.dump(params, f)

print(f"Saved model_params.json ({len(model.teams)} teams)")
