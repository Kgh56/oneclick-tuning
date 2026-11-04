-- Chiptuning-Firma: gemeinsame Einstellungen (Server und Client)
-- ModuleScript "Config" in ReplicatedStorage

local Config = {}

Config.StartMoney = 300
Config.DataStoreName = "ChiptuningFirma_v1"
Config.MaxPlots = 6 -- in den Spieleinstellungen "Max Players" auf 6 stellen

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

------------------------------------------------------------------------
-- SOUNDS
-- Die Dateien aus dem Ordner roblox/sounds bei Roblox hochladen
-- (Creator Hub → Entwicklung → Audio, oder in Studio über den Asset Manager)
-- und hier die Zahlen-IDs eintragen. Leer = Sound ist aus.
------------------------------------------------------------------------
Config.Sounds = {
	MotorTief = "", -- motor_tief.ogg   (Motor unten, Leerlauf)
	MotorHoch = "", -- motor_hoch.ogg   (Motor hohe Drehzahl)
	Turbo = "", -- turbo.ogg            (Turbo-Pfeifen)
	Abblasen = "", -- abblasen.ogg      (Abblasventil beim Schalten)
	Fehlzuendung = "", -- fehlzuendung.ogg (Knallen aus dem Auspuff)
	Reifen = "", -- reifen.ogg          (Reifenquietschen)
	Hydraulik = "", -- hydraulik.ogg    (Hebebühne)
	Umgebung = "", -- umgebung.ogg      (Wind und Vögel)
}
Config.SoundVolume = 1 -- Gesamtlautstärke der Fahrzeuge

-- Wandelt eine eingetragene ID in "rbxassetid://..." um (nil = nicht gesetzt)
function Config.SoundId(key)
	local v = Config.Sounds[key]
	if v == nil or v == "" or v == 0 then
		return nil
	end
	v = tostring(v)
	if v:match("^%d+$") then
		return "rbxassetid://" .. v
	end
	return v
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
