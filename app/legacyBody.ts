export const LEGACY_BODY = `<header>
  <h1>⚽ WC 2026 Betting Model</h1>
  <span class="badge">Poisson + Kelly</span>
</header>

<div class="tabs">
  <div class="tab active" onclick="switchTab('tippmix')">⚽ Match Bot</div>
  <div class="tab" onclick="switchTab('corners')">📐 Corner Bot</div>
  <div class="tab" onclick="switchTab('cards')">🟨 Kártya Bot</div>
  <div class="tab" onclick="switchTab('live')">🔴 Élő meccsek</div>
  <div class="tab" onclick="switchTab('history')">📊 Eredmények</div>
</div>

<div class="container">

  <!-- TAB: Tippmix.hu -->
  <div class="tab-content active" id="tab-tippmix">
    <div class="live-header">
      <div>
        <div class="card-title" style="margin:0">⚽ Match Bot — Value bet kereső</div>
        <div style="font-size:0.8rem;color:#555;margin-top:4px">Élő Tippmix odds + Poisson modell összehasonlítás. Szögletek és lesek becsült értékek (~).</div>
      </div>
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <div style="display:flex;align-items:center;gap:8px;background:#16161e;border:1px solid #2a2a3a;border-radius:8px;padding:8px 14px">
          <span style="font-size:0.85rem;color:#aaa;white-space:nowrap">Bankroll:</span>
          <input id="bankroll" type="number" value="10000" min="100" step="500"
            style="width:100px;background:transparent;border:none;color:#fff;font-size:0.95rem;font-weight:700;outline:none"
            oninput="rebuildStakes()" />
          <span style="font-size:0.85rem;color:#555">Ft</span>
        </div>
        <button class="refresh-btn" onclick="loadTippmix()">Tippmix frissítése</button>
        <button id="retrain-btn" class="refresh-btn" onclick="retrainModel()" style="background:#0a1f0a;border-color:#1a3a1a;color:#4cff91">🧠 Modell tanítása</button>
        <button class="refresh-btn" onclick="restartServer()" style="border-color:#ff6b6b;color:#ff6b6b" title="Újraindítja a szervert és frissíti az oldalt">🔄 Szerver újraindítása</button>
        <button class="refresh-btn" onclick="restartTelegram()" style="border-color:#a0b0ff;color:#a0b0ff" title="Telegram bot újraindítása">🤖 Telegram újraindítása</button>
      </div>
    </div>
    <div id="model-trained-info" style="font-size:0.75rem;color:#444;margin-bottom:8px"></div>
    <div id="retrain-panel"></div>
    <!-- Betting guide -->
    <div class="guide-panel">
      <button class="guide-toggle" onclick="toggleGuide()">📖 Mikor és mennyit fogadjak? — útmutató (kattints a megnyitáshoz)</button>
      <div class="guide-body" id="guide-body">
        <div class="guide-grid">
          <div class="guide-box">
            <h4>✅ Mikor fogadjak?</h4>
            <div class="guide-row"><span class="g-mark" style="color:#4cff91">●</span><span>Gólpiac, edge <b>≥ 7%</b> → fogadj</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#a0cc60">●</span><span>Szögletek/lesek (~), edge <b>≥ 20%</b> → fogadj (fél összeggel)</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">●</span><span>Edge &lt; 7% (gólok) vagy &lt; 20% (~) → hagyd ki</span></div>
          </div>
          <div class="guide-box">
            <h4>💰 Mennyit fogadjak?</h4>
            <div class="guide-row"><span class="g-mark">⭐</span><span>Legjobb fogadás: a <b>javasolt tét</b> (¼ Kelly) látható a kártyán</span></div>
            <div class="guide-row"><span class="g-mark">🟢</span><span>Gólpiac: javasolt tét = Kelly / 4</span></div>
            <div class="guide-row"><span class="g-mark">🟡</span><span>~becslés: javasolt tét = Kelly / 8</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">✗</span><span>Soha ne tedd fel a teljes Kelly összeget</span></div>
          </div>
          <div class="guide-box">
            <h4>⭐ Melyiket válasszam?</h4>
            <div class="guide-row"><span class="g-mark">1.</span><span>DNB (Döntetlennél visszajár) — döntetlen esetén visszakapod</span></div>
            <div class="guide-row"><span class="g-mark">2.</span><span>Gólszám O/U — független a győztestől</span></div>
            <div class="guide-row"><span class="g-mark">3.</span><span>1X2 — ha az edge nagyon magas (&gt;20%)</span></div>
            <div class="guide-note">Meccsenkénti 1 fogadás — a <b>⭐ LEGJOBB FOGADÁS</b> kártyát nézd.</div>
          </div>
          <div class="guide-box">
            <h4>❌ Mit hagyjak ki?</h4>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">✗</span><span>Pontos eredmény (túl kockázatos)</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">✗</span><span>Félidő/végeredmény kombók</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">✗</span><span>Több korreláló fogadás ugyanazon meccsen (pl. DNB + 1X2 + Hendikep egyszerre)</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">✗</span><span>~becslés fogadások 20% edge alatt</span></div>
          </div>
        </div>

        <!-- Rules table -->
        <div style="margin-top:20px;overflow-x:auto">
          <div style="font-size:0.7rem;color:#6b7aff;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Fogadási szabálytáblázat</div>
          <table style="width:100%;font-size:0.8rem;border-collapse:collapse;border:2px solid #2e3a5a">
            <thead>
              <tr style="background:#1a2240">
                <th style="padding:9px 12px;border:1px solid #2e3a5a;color:#a0b0ff;font-weight:700;white-space:nowrap">Piac típusa</th>
                <th style="padding:9px 12px;border:1px solid #2e3a5a;color:#a0b0ff;font-weight:700;white-space:nowrap">Edge %</th>
                <th style="padding:9px 12px;border:1px solid #2e3a5a;color:#a0b0ff;font-weight:700;white-space:nowrap">Döntés</th>
                <th style="padding:9px 12px;border:1px solid #2e3a5a;color:#a0b0ff;font-weight:700;white-space:nowrap">Tét</th>
                <th style="padding:9px 12px;border:1px solid #2e3a5a;color:#a0b0ff;font-weight:700;white-space:nowrap">Prioritás</th>
                <th style="padding:9px 12px;border:1px solid #2e3a5a;color:#a0b0ff;font-weight:700">Megjegyzés</th>
              </tr>
            </thead>
            <tbody>
              <tr style="background:#071a07">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">Gólpiac (O/U, DNB)</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#4cff91;font-weight:700">≥ 15%</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#0a3a0a;color:#4cff91;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">FOGADJ</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#e8e8e8">¼ Kelly</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#4cff91">⭐ Legjobb</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#888">Legerősebb szignál, elsőbbség</td>
              </tr>
              <tr style="background:#101a10">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">Gólpiac (O/U, DNB)</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#a0cc60;font-weight:700">7% – 14%</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#1a2e0a;color:#a0cc60;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">FOGADJ</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#e8e8e8">¼ Kelly</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#a0cc60">Jó</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#888">Érdemes, de ne halmozz egy meccsen</td>
              </tr>
              <tr style="background:#131316">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">Gólpiac (O/U, DNB)</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#555;font-weight:700">&lt; 7%</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#2a0a0a;color:#ff6b6b;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">HAGYD KI</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#444">—</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#444">—</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#555">Modell bizonytalansága nagyobb az edge-nél</td>
              </tr>
              <tr style="background:#1a1408">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">1X2 (győztes)</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#f0a020;font-weight:700">≥ 20%</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#2a1a00;color:#f0a020;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">FOGADJ</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#e8e8e8">¼ Kelly</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#f0a020">Közepes</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#888">Ha nincs jobb gólpiac bet</td>
              </tr>
              <tr style="background:#131316">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">1X2 (győztes)</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#555;font-weight:700">&lt; 20%</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#2a0a0a;color:#ff6b6b;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">HAGYD KI</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#444">—</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#444">—</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#555">1X2 természetesen magas variancia</td>
              </tr>
              <tr style="background:#191208">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">Szöglet / les (~becslés)</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#f0a020;font-weight:700">≥ 20%</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#2a1a00;color:#f0a020;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">FOGADJ*</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#e8e8e8">⅛ Kelly</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#f0a020">Alacsony</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#888">*Fél összeggel, közelítő modell</td>
              </tr>
              <tr style="background:#131316">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">Szöglet / les (~becslés)</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#555;font-weight:700">&lt; 20%</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#2a0a0a;color:#ff6b6b;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">HAGYD KI</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#444">—</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#444">—</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#555">Nem elég megbízható</td>
              </tr>
              <tr style="background:#1a0a0a">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">Korreláló fogadások</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#ff6b6b;font-weight:700">bármilyen</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#2a0a0a;color:#ff6b6b;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">CSAK EGYET</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#444">—</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#ff6b6b">❌ Tiltott</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#888">DNB + 1X2 + Hendikep = ugyanaz a kockázat</td>
              </tr>
              <tr style="background:#1a0a0a">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">Pontos eredmény / kombó</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#ff6b6b;font-weight:700">bármilyen</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#2a0a0a;color:#ff6b6b;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">HAGYD KI</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#444">—</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#ff6b6b">❌ Tiltott</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#888">Túl kockázatos, nagy variancia</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div id="tippmix-list">
      <div class="empty-state">
        Kattints a "Tippmix frissítése" gombra az élő oddsok betöltéséhez<br>
        <span style="font-size:0.8rem;margin-top:8px;display:block">~10 mp (headless böngésző indul)</span>
      </div>
    </div>
  </div>

  <!-- TAB: Szögletek (Corners) -->
  <div class="tab-content" id="tab-corners" style="display:none">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px">
      <div>
        <div class="card-title">📐 Corner Bot — Corner modell</div>
        <div style="font-size:0.78rem;color:#555;margin-top:4px">Önálló Poisson corner modell • Historikus szöglet adatok alapján</div>
        <div id="corner-trained-info" style="font-size:0.75rem;color:#444;margin-top:4px"></div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <button id="retrain-corners-btn" onclick="retrainCorners()" class="refresh-btn" style="border-color:#6b7aff;color:#6b7aff">🧠 Corner modell tanítása</button>
        <button onclick="loadCorners()" class="refresh-btn">⟳ Frissítés</button>
      </div>
    </div>
    <div id="retrain-corners-panel"></div>
    <div id="corners-list"><div class="empty-state">Kattints a "Frissítés" gombra a corner value betek betöltéséhez</div></div>
  </div>


  <!-- TAB: Kártyák (Cards) -->
  <div class="tab-content" id="tab-cards" style="display:none">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px">
      <div>
        <div class="card-title">🟨 Kártya Bot — Sárga lap modell</div>
        <div style="font-size:0.78rem;color:#555;margin-top:4px">Bayesian kártyaarány modell • Csapat + bíró tendenciák alapján</div>
        <div id="card-trained-info" style="font-size:0.75rem;color:#444;margin-top:4px"></div>
      </div>
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <button id="retrain-cards-btn" onclick="retrainCards()" class="refresh-btn" style="border-color:#f0c040;color:#f0c040">🧠 Kártya modell tanítása</button>
        <button onclick="loadCards()" class="refresh-btn">⟳ Frissítés</button>
      </div>
    </div>
    <div id="retrain-cards-panel"></div>
    <div id="cards-list"><div class="empty-state">Kattints a "Kártya modell tanítása" gombra az első betanításhoz, majd "Frissítés"-re</div></div>
  </div>


  <!-- TAB: Eredmények (History) -->
  <div class="tab-content" id="tab-history" style="display:none">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:10px">
      <div>
        <div class="card-title">📊 Modell pontossága — lezárt VB meccsek</div>
        <div style="font-size:0.78rem;color:#555;margin-top:4px">Minden lejátszott VB meccs: modell előrejelzés vs. valós eredmény</div>
      </div>
      <button onclick="loadHistory()" class="refresh-btn">⟳ Frissítés</button>
    </div>
    <div id="history-summary" style="margin-bottom:16px"></div>
    <div id="history-list"><div class="empty-state">Kattints a "Frissítés" gombra</div></div>
  </div>

  <!-- TAB: Live matches -->
  <div class="tab-content" id="tab-live">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
      <div>
        <div class="card-title">🔴 Élő VB meccsek</div>
        <div style="font-size:0.78rem;color:#555;margin-top:4px">Valós idejű xG + Poisson modell • Auto-frissítés 7mp-enként</div>
      </div>
      <div style="display:flex;align-items:center;gap:10px">
        <span id="live-countdown" style="font-size:0.75rem;color:#444;display:none">⟳ <span id="live-countdown-s">15</span>s</span>
        <button onclick="loadLive(false)" class="live-refresh-btn"><span class="icon">⟳</span> Frissítés</button>
      </div>
    </div>
    <!-- Live betting guide -->
    <div class="guide-panel" style="margin-bottom:20px">
      <button class="guide-toggle" onclick="toggleLiveGuide()">📖 Élő fogadás szabályok — útmutató (kattints a megnyitáshoz)</button>
      <div class="guide-body" id="live-guide-body">
        <!-- Fair odds explanation -->
        <div style="background:#0d1525;border:1px solid #2e3a5a;border-radius:8px;padding:12px 16px;margin-bottom:14px;font-size:0.82rem;line-height:1.7">
          <span style="color:#6b7aff;font-weight:700">Mi az a fair odds?</span>
          <span style="color:#aaa"> — A modell kiszámítja, mennyi az esemény valódi valószínűsége. A fair odds = </span>
          <span style="color:#fff;font-weight:700">1 ÷ valószínűség</span>
          <span style="color:#aaa">. Ha a modell szerint 65% esély van a hazai győzelemre, a fair odds = 1 ÷ 0,65 = </span>
          <span style="color:#4cff91;font-weight:700">1,54</span>
          <span style="color:#aaa">. Ez a "valódi ár" — a Tippmixnek ezt vagy ennél <b style="color:#fff">többet</b> kell kínálnia, hogy értékes legyen a fogadás.</span>
        </div>

        <div class="guide-grid">
          <div class="guide-box">
            <h4>✅ Mikor fogadjak élőben?</h4>
            <div class="guide-row"><span class="g-mark" style="color:#4cff91">●</span><span>Tippmix odds ≥ <b>fair odds × 1,10</b> (DNB / Gólszám) → fogadj</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#f0a020">●</span><span>Tippmix odds ≥ <b>fair odds × 1,15</b> (1X2) → fogadj, de kis téttel</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">●</span><span>Tippmix odds &lt; fair odds × 1,10 → ne fogadj, nincs elég margin</span></div>
            <div class="guide-note" style="margin-top:8px">Pl. fair odds 1,54 → DNB/Gólszámnál min. <b>1,69</b> kell Tippmixen (1,54 × 1,10). Az élő táblázatban a <b>MIN. ODDS</b> oszlop ezt mutatja meg.</div>
          </div>
          <div class="guide-box">
            <h4>💰 Mennyit fogadjak élőben?</h4>
            <div class="guide-row"><span class="g-mark">🟢</span><span>DNB / Gólszám: javasolt tét = Kelly × ¼</span></div>
            <div class="guide-row"><span class="g-mark">🟡</span><span>1X2 élőben: Kelly × ⅛ (nagyobb bizonytalanság)</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">✗</span><span>Soha ne fogadj a teljes Kelly összegért</span></div>
            <div class="guide-note" style="margin-top:8px">Írd be a Tippmix szorzót a KELLY TÉT kalkulátorba — megmutatja a javasolt összeget.</div>
          </div>
          <div class="guide-box">
            <h4>⭐ Melyiket válasszam élőben?</h4>
            <div class="guide-row"><span class="g-mark">1.</span><span>DNB — döntetlen esetén visszakapod a tétet, legbiztonságosabb</span></div>
            <div class="guide-row"><span class="g-mark">2.</span><span>Gólszám O/U — független a győztestől, stabil piac</span></div>
            <div class="guide-row"><span class="g-mark">3.</span><span>1X2 — csak ha modell% nagyon magas (&gt;80%) és fair × 1,15+ van</span></div>
            <div class="guide-note">A modell élő xG-t is figyelembe vesz — bízz az adatban, ne az érzéseidben.</div>
          </div>
          <div class="guide-box">
            <h4>❌ Mit hagyjak ki élőben?</h4>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">✗</span><span>Ha Tippmix odds &lt; MIN. ODDS a táblázatban → nem value bet</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">✗</span><span>Gól után azonnal: az odds már beárazta, késő</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">✗</span><span>85+ perc: nincs elég idő a valószínűség kiegyenlítésére</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">✗</span><span>Több korreláló fogadás ugyanazon a meccsen (pl. DNB + 1X2)</span></div>
          </div>
          <div class="guide-box" style="grid-column:1/-1">
            <h4>📊 Modell % — mit jelent és mikor fogadj?</h4>
            <div class="guide-row"><span class="g-mark" style="color:#6b7aff">!</span><span>A modell% <b>önmagában nem dönt</b> — az <b>edge% dönt</b>: modell% − implied% (= 1 ÷ odds). Magas modell%, de szoros odds → nincs value.</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#4cff91">✓</span><span><b>Edge ≥ 7%</b> (DNB / Gólszám) → <b style="color:#4cff91">Fogadj</b> — elegendő edge, Kelly tét szerint</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#4cff91">✓</span><span><b>Edge ≥ 10%</b> (1X2 élőben) → <b style="color:#4cff91">Fogadj</b> — 1X2-nél magasabb küszöb kell a nagyobb bizonytalanság miatt</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#f0a020">~</span><span><b>Edge 0–7%</b> → <b style="color:#f0a020">Gyenge</b> — nincs elég margin a ház ellen; legfeljebb fél Kelly, inkább kihagyni</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">✗</span><span><b>Edge &lt; 0%</b> → <b style="color:#ff6b6b">Ne fogadj</b> — a Tippmix odds rosszabb a modellnél, negatív várható érték</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#a0b0ff">!</span><span><b>Modell % önmagában nem dönt</b> — az edge dönt: modell% − implied% (= 1 ÷ odds). Magas modell%, de szoros odds → nincs value.</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#4cff91">●</span><span><b>Modell &gt;80%</b> — bármely piacra fogadható, ha edge ≥ 7%</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#f0a020">●</span><span><b>Modell 50–80%</b> — DNB / Gólszámnál edge ≥ 7% elég; 1X2-nél edge ≥ 10% kell</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">●</span><span><b>Modell &lt;50%</b> — csak ha edge ≥ 7% és az odds kifejezetten jó; kis téttel</span></div>
            <div class="guide-row"><span class="g-mark" style="color:#ff6b6b">✗</span><span><b>Kötés (parlay) soha</b> — az edge nem adódik össze, a ház marzsa fogásonként szorzódik; mindig egyedi fogadás</span></div>
            <div class="guide-note" style="margin-top:8px">Példa: 73,8% modell + 1,40 Tippmix odds → implied 71,4% → edge csak +2,4% → <b style="color:#f0a020">Gyenge, ne fogadj</b>. Ugyanaz a 73,8% + 1,55 odds → implied 64,5% → edge +9,3% → <b style="color:#4cff91">Fogadj.</b></div>
          </div>
        </div>

        <div style="margin-top:20px;overflow-x:auto">
          <div style="font-size:0.7rem;color:#6b7aff;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">Élő fogadási szabálytáblázat</div>
          <table style="width:100%;font-size:0.8rem;border-collapse:collapse;border:2px solid #2e3a5a">
            <thead>
              <tr style="background:#1a2240">
                <th style="padding:9px 12px;border:1px solid #2e3a5a;color:#a0b0ff;font-weight:700;white-space:nowrap">Piac típusa</th>
                <th style="padding:9px 12px;border:1px solid #2e3a5a;color:#a0b0ff;font-weight:700;white-space:nowrap">Min. Tippmix szorzó</th>
                <th style="padding:9px 12px;border:1px solid #2e3a5a;color:#a0b0ff;font-weight:700;white-space:nowrap">Döntés</th>
                <th style="padding:9px 12px;border:1px solid #2e3a5a;color:#a0b0ff;font-weight:700;white-space:nowrap">Tét</th>
                <th style="padding:9px 12px;border:1px solid #2e3a5a;color:#a0b0ff;font-weight:700;white-space:nowrap">Prioritás</th>
                <th style="padding:9px 12px;border:1px solid #2e3a5a;color:#a0b0ff;font-weight:700">Megjegyzés</th>
              </tr>
            </thead>
            <tbody>
              <tr style="background:#071a07">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">DNB (Döntetlennél visszajár)</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#4cff91;font-weight:700">fair odds × 1,10</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#0a3a0a;color:#4cff91;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">FOGADJ</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#e8e8e8">¼ Kelly</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#4cff91">⭐ Legjobb</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#888">Döntetlen esetén visszakapod a tétet</td>
              </tr>
              <tr style="background:#101a10">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">Gólszám O/U</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#a0cc60;font-weight:700">fair odds × 1,10</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#1a2e0a;color:#a0cc60;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">FOGADJ</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#e8e8e8">¼ Kelly</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#a0cc60">🥈 Jó</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#888">Független a győztestől, stabil</td>
              </tr>
              <tr style="background:#161208">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">1X2 élőben</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#f0a020;font-weight:700">fair odds × 1,15</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#2a1e08;color:#f0a020;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">ÓVATOSAN</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#e8e8e8">⅛ Kelly</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#f0a020">🥉 Kockázatos</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#888">Odds gyorsan mozog élőben, nagyobb margin kell</td>
              </tr>
              <tr style="background:#1a0a0a">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">Korreláló fogadások</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#ff6b6b;font-weight:700">bármilyen</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#2a0a0a;color:#ff6b6b;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">CSAK EGYET</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#444">—</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#ff6b6b">❌ Tiltott</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#888">DNB + 1X2 = ugyanaz a kockázat, ne rakd mindkettőt</td>
              </tr>
              <tr style="background:#1a0a0a">
                <td style="padding:8px 12px;border:1px solid #2e3a5a;font-weight:600">85+ perc / Tippmix &lt; MIN.</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#ff6b6b;font-weight:700">bármilyen</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a"><span style="background:#2a0a0a;color:#ff6b6b;padding:2px 10px;border-radius:4px;font-weight:700;font-size:0.75rem">HAGYD KI</span></td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#444">—</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#ff6b6b">❌ Tiltott</td>
                <td style="padding:8px 12px;border:1px solid #2e3a5a;color:#888">Nincs elég edge vagy idő a kiegyenlítésre</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <div id="live-list">
      <div class="empty-state">Kattints a 🔴 Élő meccsek fülre az élő meccsek betöltéséhez</div>
    </div>
  </div>

  <!-- TAB: All Teams -->
  <div class="tab-content" id="tab-demo">
    <div class="card-title" style="margin-bottom:16px">WC 2026 meccsek — modell valószínűségek</div>
    <div class="demo-grid" id="demo-grid"></div>
  </div>

</div>`;
