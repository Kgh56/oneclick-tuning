--[[
  Stage 1 Automatik fuer WinOLS (Lua)
  -----------------------------------
  Ablauf:
    1. Alle Kennfelder im aktuellen Projekt durchgehen
    2. Anhand des Namens einer Kategorie zuordnen (Fahrerwunsch, Begrenzer, Ladedruck ...)
    3. Nur den Volllast-Bereich anheben (sanfte Rampe, Teillast bleibt original)
    4. Werte auf Obergrenzen begrenzen
    5. Protokoll ausgeben

  VORAUSSETZUNG: Die Kennfelder muessen im Projekt definiert sein
  (DAMOS/A2L importiert, aus aehnlichem Projekt uebernommen oder per Kennfeldsuche gefunden).

  WICHTIG: Der Block "ADAPTER" unten muss an die WinOLS-Lua-Funktionen aus der
  WinOLS-Hilfe (Lua-Scripte) angepasst werden. Alles andere ist unabhaengig davon.
  Checksumme danach wie gewohnt in WinOLS korrigieren lassen!
]]

---------------------------------------------------------------------------
-- KONFIGURATION
---------------------------------------------------------------------------

-- Dry-Run: true = nur anzeigen, was geaendert wuerde, nichts schreiben
local DRY_RUN = true

-- Rampe: Unterhalb RAMP_START (Anteil vom Kennfeld-Maximum) wird nichts geaendert,
-- ab RAMP_FULL wird der volle Prozentsatz angewendet, dazwischen linear.
local RAMP_START = 0.60
local RAMP_FULL  = 0.90

-- Kategorien: Namensmuster (Lua-Patterns, Gross/Klein egal), Anhebung in %, Obergrenze (physikalisch)
-- Die Muster sind Beispiele fuer EDC17/MED17-Benennungen -> an eure Projekte anpassen!
local CATEGORIES = {
  {
    name     = "Fahrerwunsch",
    patterns = { "accped_trq", "fahrerwunsch", "driver.*wish" },
    percent  = 12,
    cap      = nil,      -- nil = keine Obergrenze
    rampe    = true,
  },
  {
    name     = "Drehmomentbegrenzer",
    patterns = { "trqlim", "engprt_trq", "momentenbegrenz", "torque.*limit" },
    percent  = 15,
    cap      = nil,
    rampe    = false,    -- Begrenzer komplett anheben
  },
  {
    name     = "Moment->Menge",
    patterns = { "fmtc_trq2q", "trq2q", "menge.*moment" },
    percent  = 10,
    cap      = 75,       -- mg/Hub, motorabhaengig!
    rampe    = true,
  },
  {
    name     = "Rauchbegrenzer",
    patterns = { "smklim", "rauchbegrenz", "smoke" },
    percent  = 10,
    cap      = 75,       -- mg/Hub
    rampe    = true,
  },
  {
    name     = "Ladedruck Soll",
    patterns = { "pcr_pdes", "ladedruck.*soll", "boost.*target" },
    percent  = 8,
    cap      = 2600,     -- hPa absolut, turboabhaengig!
    rampe    = true,
  },
  {
    name     = "Ladedruckbegrenzer",
    patterns = { "pcr_pmax", "ladedruck.*begrenz", "boost.*limit" },
    percent  = 8,
    cap      = 2700,     -- hPa
    rampe    = false,
  },
  {
    name     = "Raildruck",
    patterns = { "rail_psetpoint", "raildruck.*soll" },
    percent  = 5,
    cap      = 2000,     -- bar, systemabhaengig!
    rampe    = true,
  },
}

---------------------------------------------------------------------------
-- ADAPTER  ->  HIER AN DIE WINOLS-LUA-API ANPASSEN
-- Die rechten Seiten sind Platzhalter. Ersetze sie durch die echten
-- Funktionen aus der WinOLS-Hilfe (Stichwort "Lua").
---------------------------------------------------------------------------

local OLS = {}

-- Anzahl Kennfelder im aktuellen Projekt
function OLS.mapCount()             return winols_GetMapCount() end
-- Name des Kennfelds i (0-basiert oder 1-basiert -> laut Doku pruefen)
function OLS.mapName(i)             return winols_GetMapName(i) end
-- Groesse: Spalten (X) und Zeilen (Y)
function OLS.mapSize(i)             return winols_GetMapColumns(i), winols_GetMapRows(i) end
-- Physikalischen Wert lesen / schreiben
function OLS.getValue(i, x, y)      return winols_GetMapValue(i, x, y) end
function OLS.setValue(i, x, y, v)   winols_SetMapValue(i, x, y, v) end
-- Ausgabe ins Protokoll/Meldungsfenster
function OLS.log(text)              print(text) end

---------------------------------------------------------------------------
-- LOGIK (unabhaengig von der API)
---------------------------------------------------------------------------

local function findCategory(mapName)
  local n = string.lower(mapName or "")
  for _, cat in ipairs(CATEGORIES) do
    for _, p in ipairs(cat.patterns) do
      if string.find(n, p) then return cat end
    end
  end
  return nil
end

local function rampFactor(value, maxValue)
  if maxValue <= 0 then return 0 end
  local ratio = value / maxValue
  if ratio <= RAMP_START then return 0 end
  if ratio >= RAMP_FULL then return 1 end
  return (ratio - RAMP_START) / (RAMP_FULL - RAMP_START)
end

local function processMap(i, cat)
  local cols, rows = OLS.mapSize(i)

  -- Maximum des Kennfelds fuer die Rampe ermitteln
  local maxValue = 0
  for y = 0, rows - 1 do
    for x = 0, cols - 1 do
      local v = OLS.getValue(i, x, y)
      if v > maxValue then maxValue = v end
    end
  end

  local changed, biggest = 0, 0
  for y = 0, rows - 1 do
    for x = 0, cols - 1 do
      local old = OLS.getValue(i, x, y)
      local f = cat.rampe and rampFactor(old, maxValue) or 1
      local new = old * (1 + cat.percent / 100 * f)
      if cat.cap and new > cat.cap then new = math.max(old, cat.cap) end
      if new ~= old then
        if not DRY_RUN then OLS.setValue(i, x, y, new) end
        changed = changed + 1
        local pct = old ~= 0 and (new - old) / old * 100 or 0
        if pct > biggest then biggest = pct end
      end
    end
  end
  return changed, cols * rows, biggest
end

local function main()
  OLS.log("=== Stage 1 Automatik " .. (DRY_RUN and "(DRY-RUN, nichts geschrieben)" or "") .. " ===")
  local found = {}
  local count = OLS.mapCount()

  for i = 0, count - 1 do
    local name = OLS.mapName(i)
    local cat = findCategory(name)
    if cat then
      local changed, total, biggest = processMap(i, cat)
      OLS.log(string.format("[%s] %s: %d/%d Zellen geaendert, max +%.1f %%",
        cat.name, name, changed, total, biggest))
      found[cat.name] = true
    end
  end

  -- Warnen, wenn eine Kategorie fehlt
  for _, cat in ipairs(CATEGORIES) do
    if not found[cat.name] then
      OLS.log("WARNUNG: Kein Kennfeld fuer '" .. cat.name .. "' gefunden - Namensmuster pruefen!")
    end
  end

  OLS.log("Fertig. Checksumme korrigieren und File pruefen, bevor es rausgeht!")
end

main()
