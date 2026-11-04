-- Chiptuning-Firma: gemeinsame Einstellungen (Server und Client)
-- ModuleScript "Config" in ReplicatedStorage

local Config = {}

Config.StartMoney = 300

-- Demo-Hinweis beim Start (auf false setzen, wenn das Spiel fertig ist)
Config.ShowDemoNotice = true
Config.DemoText = "🚧 DEMO-VERSION 🚧\n\nChiptuning-Firma ist noch in Entwicklung und kann Fehler haben.\n\nDeine Ideen und Verbesserungsvorschläge sind herzlich willkommen! Schick sie uns jederzeit über den Knopf „💡 Ideen“."
Config.DataStoreName = "ChiptuningFirma_v1"
Config.MaxPlots = 12 -- Werkstätten pro Server; in den Spieleinstellungen "Server Size" auf 12 stellen

-- Die drei Kennfelder, die beim Tunen nacheinander abgestimmt werden
Config.MapNames = { "Zündzeitpunkt", "Ladedruck", "Einspritzmenge" }

Config.Stages = {
	{ Name = "Stage 1", PowerGain = 0.20, TorqueGain = 0.25, BasePay = 120, SpeedMult = 1.00 },
	{ Name = "Stage 2", PowerGain = 0.35, TorqueGain = 0.40, BasePay = 320, SpeedMult = 1.25 },
	{ Name = "Stage 3", PowerGain = 0.55, TorqueGain = 0.60, BasePay = 800, SpeedMult = 1.50 },
}

-- Kundenautos (fiktive Modelle). MinRep = ab welchem Ruf der Kunde kommt
Config.Cars = {
	{ Name = "Stadtflitzer 1.0 Turbo", Style = "hatch", Hp = 95, Nm = 175, PayMult = 0.7, MinRep = 0, Color = Color3.fromRGB(200, 200, 205) },
	{ Name = "Kompakt 1.4 Turbo", Style = "hatch", Hp = 150, Nm = 250, PayMult = 0.9, MinRep = 0, Color = Color3.fromRGB(30, 80, 160) },
	{ Name = "Familienkombi 2.0 Diesel", Style = "wagon", Hp = 150, Nm = 340, PayMult = 1.0, MinRep = 0, Color = Color3.fromRGB(40, 40, 45) },
	{ Name = "Hot Hatch GTX", Style = "hatch", Hp = 245, Nm = 370, PayMult = 1.2, MinRep = 10, Color = Color3.fromRGB(190, 20, 30) },
	{ Name = "Limousine 3.0 Diesel", Style = "sedan", Hp = 286, Nm = 650, PayMult = 1.4, MinRep = 25, Color = Color3.fromRGB(20, 40, 90) },
	{ Name = "Sportkombi 2.9 V6", Style = "wagon", Hp = 450, Nm = 600, PayMult = 1.8, MinRep = 50, Color = Color3.fromRGB(80, 90, 95) },
	{ Name = "Sportcoupé 3.8 Turbo", Style = "coupe", Hp = 580, Nm = 750, PayMult = 2.5, MinRep = 100, Color = Color3.fromRGB(240, 180, 0) },
	{ Name = "Supersportler V12", Style = "super", Hp = 780, Nm = 720, PayMult = 3.5, MinRep = 200, Color = Color3.fromRGB(10, 150, 80) },
}

-- Upgrades im Werkstatt-Shop (Reihenfolge = Anzeige im Shop)
Config.Upgrades = {
	{ Id = "Bay2", Name = "2. Hebebühne", Price = 800, Desc = "Zwei Kunden gleichzeitig bedienen." },
	{ Id = "Stage2", Name = "Stage-2-Software", Price = 2000, Desc = "Kunden buchen jetzt auch Stage 2 – mehr Geld pro Auftrag." },
	{ Id = "Laptop", Name = "Profi-Tuning-Laptop", Price = 2500, Desc = "Die grüne Zone beim Abstimmen wird breiter." },
	{ Id = "Werbung", Name = "Werbung schalten", Price = 3500, Desc = "Kunden kommen doppelt so oft." },
	{ Id = "Bay3", Name = "3. Hebebühne", Price = 4000, Requires = "Bay2", Desc = "Drei Kunden gleichzeitig." },
	{ Id = "Dyno", Name = "Leistungsprüfstand", Price = 6000, Desc = "+25 % Bezahlung. Jedes Auto kommt nach dem Tunen auf die Rolle." },
	{ Id = "Azubi", Name = "Azubi einstellen", Price = 9000, Desc = "Tunt wartende Autos automatisch (Ergebnis: okay)." },
	{ Id = "Bay4", Name = "4. Hebebühne", Price = 12000, Requires = "Bay3", Desc = "Vier Kunden gleichzeitig." },
	{ Id = "Stage3", Name = "Stage-3-Software", Price = 15000, Requires = "Stage2", Desc = "Die großen Aufträge: Stage 3 mit Top-Bezahlung." },
	{ Id = "PopBang", Name = "Pop & Bang Software", Price = 5000, Desc = "Kunden buchen Pop & Bang (+40 % Geld). Dein Firmenwagen knallt beim Gaswegnehmen." },
}

------------------------------------------------------------------------
-- ROBUX-SHOP
-- Die Artikel im Creator Hub anlegen (Spiel → Monetization → Passes
-- bzw. Developer Products) und hier die IDs eintragen.
-- Id = 0 heißt: noch nicht eingerichtet, der Knopf zeigt "Bald verfügbar".
-- Den Robux-Preis legst du im Creator Hub fest; das Spiel liest ihn
-- automatisch aus. PriceHint wird nur angezeigt, solange das nicht klappt.
------------------------------------------------------------------------
Config.GamePasses = {
	{ Key = "DoubleMoney", Id = 0, PriceHint = 199, Name = "💰 Doppeltes Geld", Desc = "Jeder Auftrag zahlt doppelt – für immer." },
	{ Key = "VIP", Id = 0, PriceHint = 149, Name = "⭐ VIP-Werkstatt", Desc = "Goldenes Firmenschild, VIP-Titel über dem Kopf und +10 % Geld." },
	{ Key = "Turbo", Id = 0, PriceHint = 99, Name = "🚀 Turbo-Kundschaft", Desc = "Kunden kommen doppelt so schnell (zusätzlich zur Werbung)." },
}

Config.Products = {
	{ Key = "Cash5k", Id = 0, PriceHint = 49, Money = 5000, Name = "Geldpaket S", Desc = "+5.000 € sofort aufs Firmenkonto." },
	{ Key = "Cash25k", Id = 0, PriceHint = 149, Money = 25000, Name = "Geldpaket L", Desc = "+25.000 € sofort aufs Firmenkonto." },
}

Config.DoubleMoneyMult = 2
Config.VipMult = 1.1
Config.TurboMult = 0.5 -- Kundenabstand wird halbiert

------------------------------------------------------------------------

-- Teststrecke (Oval): zwei Geraden + zwei Halbkreise
Config.Track = { CenterZ = -450, HalfLength = 250, Radius = 150, Width = 30 }

-- Fahren
Config.TestDriveSeconds = 75 -- Dauer einer Probefahrt
Config.TestDriveTip = 0.15 -- Trinkgeld-Anteil nach der Probefahrt
Config.TestDriveMinSeconds = 15 -- so lange muss man fahren für Trinkgeld
Config.CompanyCar = { Name = "Firmenwagen", Style = "coupe", Hp = 220, Nm = 350, Color = Color3.fromRGB(255, 140, 0) }
Config.DayLengthMinutes = 24 -- ein Tag-Nacht-Zyklus

-- Leben in der Stadt (läuft auf jedem Client)
Config.TrafficCars = 18 -- Autos im Straßenverkehr
Config.TrafficSpeed = 42 -- Studs pro Sekunde
Config.Pedestrians = 26 -- Fußgänger
Config.NpcScale = 0.85 -- Größe der Fahrer im Auto (Fußgänger haben normale Größe)

-- Fahrwerte aus der Leistung (Studs pro Sekunde)
function Config.DriveStats(hp)
	return {
		TopSpeed = 60 + hp * 0.13,
		Accel = 18 + hp * 0.06,
	}
end

-- Studs/s -> km/h (gefühlt passend zur Roblox-Größe)
Config.KmhFactor = 1.25

-- Extras beim Fahren
Config.PopBangChance = 0.35 -- Anteil Kunden, die Pop & Bang wollen (wenn freigeschaltet)
Config.PopBangPay = 1.4
Config.NitroSeconds = 3
Config.NitroCooldown = 12
Config.NitroBoost = 1.3 -- Höchstgeschwindigkeit x
Config.LaunchRpm = 4800

------------------------------------------------------------------------
-- SOUNDS
-- EINFACH: Die Datei roblox/sounds/alle_sounds.ogg einmal bei Roblox
-- hochladen (Creator Hub → Entwicklung → Audio, oder in Studio über den
-- Asset Manager) und die Zahlen-ID hier bei SoundFile eintragen. Fertig –
-- alle 21 Sounds kommen aus dieser einen Datei.
------------------------------------------------------------------------
Config.SoundFile = "" -- z. B. "1234567890"

-- Inhalt der Sammeldatei (von tools/make_sounds.py erzeugt):
-- Name = { Start in s, Länge in s, Schleife }
Config.SoundSprite = {
	MotorTief = { 0.3, 2.0, true },
	MotorHoch = { 2.6, 2.0, true },
	Turbo = { 4.9, 2.0, true },
	Reifen = { 7.2, 2.0, true },
	Hydraulik = { 9.5, 2.0, true },
	Umgebung = { 11.8, 24.0, true },
	Werkstatt = { 36.1, 12.0, true },
	Abblasen = { 48.4, 0.75, false },
	Fehlzuendung = { 49.45, 0.9, false },
	Hupe = { 50.65, 0.75, false },
	Kasse = { 51.7, 0.9, false },
	LevelUp = { 52.9, 1.3, false },
	Klick = { 54.5, 0.06, false },
	PiepKurz = { 54.86, 0.25, false },
	PiepLang = { 55.41, 0.7, false },
	Jubel = { 56.41, 4.0, false },
	Tuer = { 60.71, 0.45, false },
	Aufprall = { 61.46, 0.9, false },
	Schluessel = { 62.66, 0.9, false },
	Blitzer = { 63.86, 0.7, false },
	Schlagschrauber = { 64.86, 1.1, false },
}

-- Optional: einzelne Dateien statt der Sammeldatei (leer = Sammeldatei)
Config.Sounds = {
	MotorTief = "",
	MotorHoch = "",
	Turbo = "",
	Abblasen = "",
	Fehlzuendung = "",
	Reifen = "",
	Hydraulik = "",
	Umgebung = "",
	Hupe = "",
}
Config.SoundVolume = 1 -- Gesamtlautstärke der Fahrzeuge

-- Wandelt eine eingetragene ID in "rbxassetid://..." um (nil = nicht gesetzt)
local function toAsset(v)
	if v == nil or v == "" or v == 0 then
		return nil
	end
	v = tostring(v)
	if v:match("^%d+$") then
		return "rbxassetid://" .. v
	end
	return v
end

-- Einzelne Datei für diesen Sound (nil = nicht gesetzt)
function Config.SoundId(key)
	return toAsset(Config.Sounds[key])
end

-- Sammeldatei
function Config.SoundFileId()
	return toAsset(Config.SoundFile)
end

-- Gibt es diesen Sound (einzeln oder in der Sammeldatei)?
function Config.HasSound(key)
	return Config.SoundId(key) ~= nil or (Config.SoundFileId() ~= nil and Config.SoundSprite[key] ~= nil)
end

------------------------------------------------------------------------
-- TESTEN
-- In Roblox Studio startest du automatisch mit StudioMoney.
-- Der Besitzer des Spiels (und alle IDs in AdminUserIds) sieht im Spiel
-- Admin-Knöpfe für Testgeld und Ruf.
------------------------------------------------------------------------
Config.StudioMoney = 1000000
Config.AdminUserIds = {} -- z. B. { 123456789 }
Config.AdminMoneyStep = 100000
Config.AdminRepStep = 50

------------------------------------------------------------------------
-- ACTION
------------------------------------------------------------------------
Config.Records = {
	speed = { Name = "Höchstgeschwindigkeit", Unit = "km/h", Lower = false, Reward = 500 },
	jump = { Name = "Weitester Sprung", Unit = "m", Lower = false, Reward = 500 },
	slalom = { Name = "Slalom", Unit = "s", Lower = true, Reward = 500 },
	lap = { Name = "Runde Teststrecke", Unit = "s", Lower = true, Reward = 500 },
}
Config.RecordOrder = { "speed", "jump", "slalom", "lap" }
Config.WrenchReward = 1000 -- pro goldenem Schraubenschlüssel
Config.WrenchBonus = 25000 -- wenn alle gefunden sind

------------------------------------------------------------------------
-- LEVEL, BELOHNUNGEN, AUFTRÄGE
------------------------------------------------------------------------
-- Erfahrungspunkte für Level n -> n+1
function Config.XPForLevel(n)
	return 80 + n * 40
end

-- Level und Fortschritt aus Gesamt-XP
function Config.LevelFromXP(xp)
	local level = 1
	local need = Config.XPForLevel(1)
	while xp >= need do
		xp -= need
		level += 1
		need = Config.XPForLevel(level)
	end
	return level, xp, need
end

Config.XP = { Tune = 20, TuneStage = 10, Perfect = 10, Azubi = 5, TestDrive = 10, Record = 25, Wrench = 30, Quest = 100, RaceWin = 80, RaceFinish = 25, Daily = 20 }
Config.LevelUpMoney = 750 -- x Level

-- Tägliche Belohnung (Tag 1..7, danach wieder von vorn)
Config.DailyRewards = { 1000, 1500, 2000, 3000, 4000, 5000, 15000 }

-- Tagesaufträge: drei zufällige pro Tag
Config.QuestPool = {
	{ Id = "tune", Text = "Tune %d Autos", Min = 4, Max = 8 },
	{ Id = "perfect", Text = "Schaffe %d perfekte Abstimmungen", Min = 2, Max = 4 },
	{ Id = "jump", Text = "Spring %d m weit", Min = 25, Max = 55, Single = true },
	{ Id = "speed", Text = "Fahr %d km/h am Blitzer", Min = 140, Max = 230, Single = true },
	{ Id = "testdrive", Text = "Mach %d Probefahrten", Min = 2, Max = 3 },
	{ Id = "slalom", Text = "Fahr den Slalom unter %d s", Min = 35, Max = 50, Single = true, Lower = true },
	{ Id = "race", Text = "Fahr %d Rennen zu Ende", Min = 1, Max = 2 },
	{ Id = "money", Text = "Verdien %d € mit Aufträgen", Min = 2000, Max = 6000 },
}
Config.QuestReward = 2500
Config.QuestBonus = 6000 -- alle drei erledigt

------------------------------------------------------------------------
-- GARAGE: Firmenwagen gestalten
------------------------------------------------------------------------
Config.GarageItems = {
	-- Lack
	{ Id = "lack_orange", Cat = "Lack", Name = "Orange", Price = 0, Color = Color3.fromRGB(255, 140, 0) },
	{ Id = "lack_rot", Cat = "Lack", Name = "Rennrot", Price = 1500, Color = Color3.fromRGB(200, 15, 25) },
	{ Id = "lack_schwarz", Cat = "Lack", Name = "Tiefschwarz", Price = 1500, Color = Color3.fromRGB(18, 18, 20) },
	{ Id = "lack_weiss", Cat = "Lack", Name = "Perlweiß", Price = 1500, Color = Color3.fromRGB(240, 240, 238) },
	{ Id = "lack_blau", Cat = "Lack", Name = "Racing-Blau", Price = 1500, Color = Color3.fromRGB(20, 70, 200) },
	{ Id = "lack_gruen", Cat = "Lack", Name = "British Green", Price = 2000, Color = Color3.fromRGB(10, 80, 45) },
	{ Id = "lack_gelb", Cat = "Lack", Name = "Signalgelb", Price = 2000, Color = Color3.fromRGB(255, 205, 0) },
	{ Id = "lack_lila", Cat = "Lack", Name = "Violett", Price = 2500, Color = Color3.fromRGB(110, 40, 170) },
	{ Id = "lack_mint", Cat = "Lack", Name = "Mint", Price = 2500, Color = Color3.fromRGB(110, 230, 190) },
	{ Id = "lack_silber", Cat = "Lack", Name = "Silber", Price = 2000, Color = Color3.fromRGB(175, 180, 188) },
	-- Felgen
	{ Id = "felge_chrom", Cat = "Felgen", Name = "Chrom", Price = 0, Color = Color3.fromRGB(205, 208, 215) },
	{ Id = "felge_schwarz", Cat = "Felgen", Name = "Schwarz matt", Price = 1000, Color = Color3.fromRGB(30, 30, 33) },
	{ Id = "felge_gold", Cat = "Felgen", Name = "Gold", Price = 2500, Color = Color3.fromRGB(215, 170, 50) },
	{ Id = "felge_rot", Cat = "Felgen", Name = "Rot", Price = 1500, Color = Color3.fromRGB(200, 25, 30) },
	{ Id = "felge_bronze", Cat = "Felgen", Name = "Bronze", Price = 2000, Color = Color3.fromRGB(150, 100, 50) },
	-- Unterbodenbeleuchtung
	{ Id = "neon_aus", Cat = "Neon", Name = "Aus", Price = 0 },
	{ Id = "neon_blau", Cat = "Neon", Name = "Blau", Price = 3000, Color = Color3.fromRGB(40, 120, 255) },
	{ Id = "neon_pink", Cat = "Neon", Name = "Pink", Price = 3000, Color = Color3.fromRGB(255, 40, 180) },
	{ Id = "neon_gruen", Cat = "Neon", Name = "Grün", Price = 3000, Color = Color3.fromRGB(40, 255, 100) },
	{ Id = "neon_orange", Cat = "Neon", Name = "Orange", Price = 3000, Color = Color3.fromRGB(255, 130, 20) },
	-- Heckflügel
	{ Id = "fluegel_aus", Cat = "Flügel", Name = "Ohne", Price = 0 },
	{ Id = "fluegel_an", Cat = "Flügel", Name = "GT-Flügel", Price = 4000 },
	-- Karosserie
	{ Id = "form_coupe", Cat = "Form", Name = "Coupé", Price = 0, Style = "coupe" },
	{ Id = "form_hatch", Cat = "Form", Name = "Hot Hatch", Price = 5000, Style = "hatch" },
	{ Id = "form_sedan", Cat = "Form", Name = "Limousine", Price = 6000, Style = "sedan" },
	{ Id = "form_wagon", Cat = "Form", Name = "Kombi", Price = 6000, Style = "wagon" },
	{ Id = "form_super", Cat = "Form", Name = "Supersportler", Price = 30000, Style = "super" },
}
Config.GarageDefaults = { Lack = "lack_orange", Felgen = "felge_chrom", Neon = "neon_aus", ["Flügel"] = "fluegel_aus", Form = "form_coupe" }
Config.GarageCats = { "Lack", "Felgen", "Neon", "Flügel", "Form" }

function Config.GetGarageItem(id)
	for _, it in ipairs(Config.GarageItems) do
		if it.Id == id then
			return it
		end
	end
	return nil
end

------------------------------------------------------------------------
-- SCHNELLREISE und RENNEN
------------------------------------------------------------------------
Config.TravelPoints = {
	{ Id = "werkstatt", Name = "🔧 Meine Werkstatt" },
	{ Id = "strecke", Name = "🏁 Teststrecke", Pos = Vector3.new(0, 4, -250) },
	{ Id = "stunt", Name = "🚀 Stuntpark", Pos = Vector3.new(160, 4, -325) },
	{ Id = "slalom", Name = "🔶 Slalom", Pos = Vector3.new(-155, 4, -325) },
	{ Id = "see", Name = "🌊 See", Pos = Vector3.new(650, 4, 300) },
	{ Id = "stadt", Name = "🏙️ Stadt / Spawn", Pos = Vector3.new(0, 4, 80) },
}

Config.RaceLaps = 2
Config.RaceLobbySeconds = 20
Config.RacePrizes = { 6000, 3500, 2000 } -- Platz 1–3, sonst RaceFinishPrize
Config.RaceFinishPrize = 1000

Config.CustomerInterval = 14 -- Sekunden zwischen Kunden
Config.CustomerIntervalAds = 7 -- mit Werbung
Config.ZoneWidth = 0.16 -- Breite der grünen Zone (Anteil des Balkens)
Config.ZoneWidthLaptop = 0.26
Config.AzubiInterval = 20
Config.DynoBonus = 1.25

Config.Score = { Perfect = 1, Good = 0.6, Bad = 0.15 }

function Config.GetUpgrade(id)
	for _, up in ipairs(Config.Upgrades) do
		if up.Id == id then
			return up
		end
	end
	return nil
end

function Config.GetPassByKey(key)
	for _, p in ipairs(Config.GamePasses) do
		if p.Key == key then
			return p
		end
	end
	return nil
end

-- Bewertet, wo die Nadel gestoppt wurde
function Config.Rate(pos, center, width)
	local d = math.abs(pos - center)
	if d <= width / 2 then
		return "Perfect"
	elseif d <= width then
		return "Good"
	end
	return "Bad"
end

-- 12345 -> "12.345"
function Config.Format(n)
	local s = tostring(math.floor(n))
	local neg = s:sub(1, 1) == "-"
	if neg then
		s = s:sub(2)
	end
	local out = s:reverse():gsub("(%d%d%d)", "%1."):reverse()
	if out:sub(1, 1) == "." then
		out = out:sub(2)
	end
	return (neg and "-" or "") .. out
end

return Config
