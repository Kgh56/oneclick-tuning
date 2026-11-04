-- Automodelle für Werkstatt, Verkehr und Spieler
-- ModuleScript "Cars" in ReplicatedStorage (Server und Client bauen damit Autos)
--
-- Koordinaten relativ zur Karosseriemitte. Die Karosseriemitte liegt 1.7 Studs
-- über dem Boden, die Front zeigt nach -Z. Räder hängen über Motor6D an der
-- Wurzel bzw. am Fahrgestell; gedreht und gelenkt werden sie von LifeClient
-- bzw. DriveClient (nur optisch, ohne Netzwerkverkehr).

local CollectionService = game:GetService("CollectionService")

local Util = require(script.Parent:WaitForChild("Util"))
local part, wedge = Util.part, Util.wedge

local Cars = {}

Cars.BODY_HEIGHT = 1.7 -- Karosseriemitte über Boden
Cars.CHASSIS_HEIGHT = 0.9 -- Mitte des Fahrgestells (fahrbares Auto) über Boden
Cars.WHEEL_RADIUS = 1.2
Cars.TAG = "AnimCar" -- Autos mit diesem Tag bekommen drehende Räder

-- Karosserieformen. Längen in Studs, Front bei -L/2.
-- Hood/Wind/Roof/Rear = Länge von Motorhaube, Frontscheibe, Dach, Heckscheibe
local STYLES = {
	hatch = { L = 10.6, W = 6.0, Hood = 2.6, Wind = 1.9, Roof = 3.6, Rear = 1.6, Cabin = 1.45, Belt = 0.8, Bottom = -0.8, Axle = 3.4 },
	sedan = { L = 12.4, W = 6.0, Hood = 3.2, Wind = 2.0, Roof = 3.0, Rear = 1.8, Cabin = 1.4, Belt = 0.8, Bottom = -0.8, Axle = 4.0 },
	wagon = { L = 12.6, W = 6.0, Hood = 3.0, Wind = 2.0, Roof = 5.6, Rear = 0.9, Cabin = 1.45, Belt = 0.8, Bottom = -0.8, Axle = 4.1 },
	coupe = { L = 12.0, W = 6.1, Hood = 3.6, Wind = 2.4, Roof = 1.9, Rear = 2.6, Cabin = 1.25, Belt = 0.7, Bottom = -0.85, Axle = 3.9, Sport = true },
	super = { L = 12.4, W = 6.4, Hood = 2.8, Wind = 2.8, Roof = 1.3, Rear = 3.5, Cabin = 1.05, Belt = 0.55, Bottom = -0.95, Axle = 4.0, Sport = true },
}
Cars.STYLES = STYLES

local TIRE = Color3.fromRGB(24, 24, 26)
local TRIM = Color3.fromRGB(28, 28, 32)
local CHROME = Color3.fromRGB(205, 208, 215)
local GLASS = Color3.fromRGB(22, 30, 40)

local PLATE_LETTERS = { "CT", "OC", "TN", "M", "B", "HH", "S", "K" }

local function build(def, m, open)
	local st = STYLES[def.Style or "sedan"] or STYLES.sedan
	local L, W = st.L, st.W
	local belt, bottom = st.Belt, st.Bottom
	local paint = def.Color
	local rng = Random.new()

	local function P(name, size, cf, color, material, extra)
		local props = {
			Name = name,
			Size = size,
			CFrame = cf,
			Color = color,
			Material = material or Enum.Material.SmoothPlastic,
			CanCollide = false,
			Parent = m,
		}
		for k, v in pairs(extra or {}) do
			props[k] = v
		end
		if math.max(size.X, size.Y, size.Z) < 1.6 then
			props.CastShadow = false -- Kleinteile ohne Schatten (schneller)
		end
		return part(props)
	end
	local function lack(name, size, cf)
		return P(name, size, cf, paint, Enum.Material.SmoothPlastic, { Reflectance = 0.15 })
	end
	local function W_(name, size, cf, color, material, extra)
		local props = {
			Name = name,
			Size = size,
			CFrame = cf,
			Color = color,
			Material = material or Enum.Material.SmoothPlastic,
			CanCollide = false,
			Parent = m,
		}
		for k, v in pairs(extra or {}) do
			props[k] = v
		end
		return wedge(props)
	end

	------------------------------------------------------------ Karosserie
	local lowerTop = belt - 0.5
	lack("Karosserie", Vector3.new(W, lowerTop - bottom, L), CFrame.new(0, (lowerTop + bottom) / 2, 0))
	lack("Guertel", Vector3.new(W, 0.5, L - 1.6), CFrame.new(0, belt - 0.25, 0))
	-- abgeschrägte Front und Heckkante
	W_("Nase", Vector3.new(W, 0.5, 0.8), CFrame.new(0, belt - 0.25, -L / 2 + 0.4), paint, nil, { Reflectance = 0.15 })
	W_("Heckkante", Vector3.new(W, 0.5, 0.8), CFrame.new(0, belt - 0.25, L / 2 - 0.4) * CFrame.Angles(0, math.pi, 0), paint, nil, { Reflectance = 0.15 })

	------------------------------------------------------------ Kabine
	local cabW = W - 0.7
	local zW = -L / 2 + st.Hood
	local zRoof = zW + st.Wind
	local zRoofEnd = zRoof + st.Roof
	local roofTop = belt + st.Cabin
	local glassProps = { Transparency = 0.35, Reflectance = 0.15 }

	-- Innenraum (durch die Scheiben sichtbar)
	P("Innenraum", Vector3.new(cabW - 0.1, 0.06, st.Wind + st.Roof + 0.4), CFrame.new(0, belt + 0.03, zRoof + st.Roof / 2 - st.Wind / 2), Color3.fromRGB(30, 30, 33))
	P("Armaturenbrett", Vector3.new(cabW - 0.2, 0.35, 0.7), CFrame.new(0, belt + 0.2, zW + st.Wind * 0.55), Color3.fromRGB(22, 22, 25))
	local seatZ = zRoof + 0.9
	for _, x in ipairs({ -1.3, 1.3 }) do
		local backH = math.min(1.3, st.Cabin - 0.15)
		P("Sitzlehne", Vector3.new(1.4, backH, 0.3), CFrame.new(x, belt + backH / 2, seatZ + 0.75), Color3.fromRGB(18, 18, 20), Enum.Material.Fabric)
	end
	local steering = P(
		"Lenkrad",
		Vector3.new(0.12, 0.9, 0.9),
		CFrame.new(-1.3, belt + 0.55, seatZ - 0.9) * CFrame.Angles(0, math.rad(90), 0) * CFrame.Angles(0, 0, math.rad(-25)),
		Color3.fromRGB(15, 15, 15),
		nil,
		{ Shape = Enum.PartType.Cylinder }
	)

	if not open then
		W_("Frontscheibe", Vector3.new(cabW, st.Cabin, st.Wind), CFrame.new(0, belt + st.Cabin / 2, zW + st.Wind / 2), GLASS, Enum.Material.Glass, glassProps)
		lack("Dach", Vector3.new(cabW, 0.18, st.Roof), CFrame.new(0, roofTop - 0.09, zRoof + st.Roof / 2))
		W_("Heckscheibe", Vector3.new(cabW, st.Cabin, st.Rear), CFrame.new(0, belt + st.Cabin / 2, zRoofEnd + st.Rear / 2) * CFrame.Angles(0, math.pi, 0), GLASS, Enum.Material.Glass, glassProps)
		for _, s in ipairs({ -1, 1 }) do
			P("Seitenscheibe", Vector3.new(0.1, st.Cabin - 0.18, st.Roof), CFrame.new(s * (cabW / 2 - 0.05), belt + (st.Cabin - 0.18) / 2, zRoof + st.Roof / 2), GLASS, Enum.Material.Glass, glassProps)
			if st.Roof > 2.5 then
				P("BSaeule", Vector3.new(0.14, st.Cabin - 0.18, 0.35), CFrame.new(s * (cabW / 2 - 0.03), belt + (st.Cabin - 0.18) / 2, zRoof + 2.2), TRIM)
			end
			if def.Style == "wagon" then
				P("Dachreling", Vector3.new(0.15, 0.15, st.Roof - 0.6), CFrame.new(s * (cabW / 2 - 0.4), roofTop + 0.08, zRoof + st.Roof / 2), Color3.fromRGB(40, 40, 44), Enum.Material.Metal)
			end
		end
	else
		-- Cabrio: niedrige Frontscheibe und Überrollbügel
		W_("Frontscheibe", Vector3.new(cabW, 1.0, 1.3), CFrame.new(0, belt + 0.5, zW + 0.65), GLASS, Enum.Material.Glass, { Transparency = 0.45, Reflectance = 0.15 })
		P("Scheibenrahmen", Vector3.new(cabW, 0.12, 0.15), CFrame.new(0, belt + 1.02, zW + 1.3), TRIM)
		local zBar = seatZ + 1.3
		for _, s in ipairs({ -1, 1 }) do
			P("Buegel", Vector3.new(0.25, 1.1, 0.25), CFrame.new(s * (cabW / 2 - 0.5), belt + 0.55, zBar), CHROME, Enum.Material.Metal)
		end
		P("BuegelOben", Vector3.new(cabW - 0.75, 0.25, 0.25), CFrame.new(0, belt + 1.1, zBar), CHROME, Enum.Material.Metal)
	end

	------------------------------------------------------------ Front
	P("Frontschuerze", Vector3.new(W + 0.1, 0.7, 0.45), CFrame.new(0, bottom + 0.35, -L / 2 - 0.05), TRIM)
	local grilleY = (bottom + 0.7 + lowerTop) / 2
	P("Grill", Vector3.new(W * 0.42, math.max(0.3, lowerTop - bottom - 0.85), 0.08), CFrame.new(0, grilleY, -L / 2 - 0.03), Color3.fromRGB(12, 12, 14))
	P("Grillspange", Vector3.new(W * 0.42, 0.06, 0.1), CFrame.new(0, grilleY, -L / 2 - 0.05), CHROME, Enum.Material.Metal)
	P("Emblem", Vector3.new(0.08, 0.45, 0.45), CFrame.new(0, grilleY + 0.05, -L / 2 - 0.08) * CFrame.Angles(0, math.rad(90), 0), CHROME, Enum.Material.Metal, { Shape = Enum.PartType.Cylinder })

	local headlights = {}
	for _, s in ipairs({ -1, 1 }) do
		local x = s * (W / 2 - 0.95)
		P("Scheinwerferglas", Vector3.new(1.4, 0.42, 0.15), CFrame.new(x, belt - 0.62, -L / 2 - 0.02), Color3.fromRGB(200, 210, 220), Enum.Material.Glass, { Transparency = 0.4, Reflectance = 0.3 })
		table.insert(headlights, P("Scheinwerfer", Vector3.new(1.1, 0.18, 0.1), CFrame.new(x, belt - 0.6, -L / 2 + 0.02), Color3.fromRGB(255, 250, 230), Enum.Material.Neon))
		P("Tagfahrlicht", Vector3.new(1.3, 0.06, 0.1), CFrame.new(x, belt - 0.88, -L / 2 - 0.01), Color3.fromRGB(235, 245, 255), Enum.Material.Neon)
	end

	------------------------------------------------------------ Heck
	P("Heckschuerze", Vector3.new(W + 0.1, 0.7, 0.45), CFrame.new(0, bottom + 0.35, L / 2 + 0.05), TRIM)
	P("Rueckleuchtenband", Vector3.new(W - 1.4, 0.1, 0.08), CFrame.new(0, belt - 0.55, L / 2 + 0.03), Color3.fromRGB(130, 8, 12), Enum.Material.Neon)
	for _, s in ipairs({ -1, 1 }) do
		P("Ruecklicht", Vector3.new(1.1, 0.34, 0.1), CFrame.new(s * (W / 2 - 0.75), belt - 0.6, L / 2 + 0.03), Color3.fromRGB(130, 8, 12), Enum.Material.Neon)
	end
	-- Blinker (werden von LifeClient/DriveClient eingeschaltet)
	for _, s in ipairs({ -1, 1 }) do
		local side = s < 0 and "L" or "R"
		P("BlinkerV" .. side, Vector3.new(0.35, 0.2, 0.08), CFrame.new(s * (W / 2 - 0.22), belt - 0.62, -L / 2 - 0.03), Color3.fromRGB(110, 65, 10))
		P("BlinkerH" .. side, Vector3.new(0.35, 0.2, 0.08), CFrame.new(s * (W / 2 - 0.22), belt - 0.85, L / 2 + 0.03), Color3.fromRGB(110, 65, 10))
	end
	P("Bremslicht", Vector3.new(1.2, 0.08, 0.06), CFrame.new(0, (open and belt or roofTop) - 0.12, (open and L / 2 - 0.5) or (zRoofEnd + 0.2)), Color3.fromRGB(90, 5, 8), Enum.Material.Neon)
	local nExhaust = st.Sport and 4 or 2
	for i = 1, nExhaust do
		local x = (nExhaust == 2) and ((i == 1) and -1.6 or 1.6) or ({ -2.0, -1.4, 1.4, 2.0 })[i]
		P("Auspuff", Vector3.new(0.6, 0.38, 0.38), CFrame.new(x, bottom + 0.3, L / 2 + 0.2) * CFrame.Angles(0, math.rad(90), 0), CHROME, Enum.Material.Metal, { Shape = Enum.PartType.Cylinder })
	end
	if st.Sport then
		P("Diffusor", Vector3.new(W - 2.4, 0.25, 0.35), CFrame.new(0, bottom + 0.12, L / 2 + 0.1), Color3.fromRGB(15, 15, 17))
		P("Frontlippe", Vector3.new(W, 0.08, 0.5), CFrame.new(0, bottom + 0.04, -L / 2 - 0.1), Color3.fromRGB(15, 15, 17))
	end
	if def.Wing or (def.Wing == nil and def.Hp and def.Hp >= 400) then
		local wingZ = (def.Style == "wagon") and (zRoofEnd - 0.2) or (L / 2 - 0.6)
		local wingY = (def.Style == "wagon") and (roofTop + 0.1) or (belt + 0.65)
		P("Fluegel", Vector3.new(W - 0.4, 0.12, 1.1), CFrame.new(0, wingY, wingZ), Color3.fromRGB(18, 18, 20))
		if def.Style ~= "wagon" then
			for _, s in ipairs({ -1, 1 }) do
				P("FluegelStuetze", Vector3.new(0.15, 0.6, 0.35), CFrame.new(s * 1.8, belt + 0.3, wingZ), Color3.fromRGB(18, 18, 20))
			end
		end
	end

	-- Kennzeichen
	local plateText = PLATE_LETTERS[rng:NextInteger(1, #PLATE_LETTERS)] .. " · " .. tostring(rng:NextInteger(10, 99)) .. tostring(rng:NextInteger(100, 999))
	for _, s in ipairs({ -1, 1 }) do
		local plate = P("Kennzeichen", Vector3.new(1.7, 0.42, 0.05), CFrame.new(0, bottom + 0.95, s * (L / 2 + 0.3)), Color3.fromRGB(240, 240, 240))
		local tl = Util.textGui(plate, s < 0 and Enum.NormalId.Front or Enum.NormalId.Back, plateText, Color3.fromRGB(15, 15, 15), Color3.fromRGB(240, 240, 240), Enum.Font.GothamBold)
		tl.Parent.PixelsPerStud = 60
	end

	------------------------------------------------------------ Seiten
	for _, s in ipairs({ -1, 1 }) do
		lack("Spiegel", Vector3.new(0.5, 0.32, 0.45), CFrame.new(s * (W / 2 + 0.2), belt + 0.25, zW + 0.45))
		P("Spiegelglas", Vector3.new(0.4, 0.24, 0.05), CFrame.new(s * (W / 2 + 0.2), belt + 0.25, zW + 0.69), Color3.fromRGB(150, 170, 190), Enum.Material.Glass, { Reflectance = 0.6 })
		P("Seitenschweller", Vector3.new(0.15, 0.3, 2 * st.Axle - 2.8), CFrame.new(s * (W / 2 + 0.03), bottom + 0.15, 0), TRIM)
		for _, zd in ipairs({ zW + 0.25, zRoof + math.min(st.Roof, 2.4) }) do
			P("Tuerfuge", Vector3.new(0.04, lowerTop - bottom + 0.3, 0.05), CFrame.new(s * (W / 2 + 0.01), (lowerTop + bottom) / 2 + 0.15, zd), Color3.fromRGB(20, 20, 22))
		end
		P("Tuergriff", Vector3.new(0.06, 0.1, 0.45), CFrame.new(s * (W / 2 + 0.03), belt - 0.4, zRoof + math.min(st.Roof, 2.4) - 0.6), CHROME, Enum.Material.Metal)
	end

	------------------------------------------------------------ Räder
	local wheels = {}
	local tireW = st.Sport and 1.15 or 1.0
	local rimColor = def.RimColor or ((def.Hp and def.Hp >= 400) and Color3.fromRGB(38, 38, 42) or CHROME)
	local idx = 0
	for _, z in ipairs({ -st.Axle, st.Axle }) do
		for _, s in ipairs({ -1, 1 }) do
			idx += 1
			local x = s * (W / 2 + 0.05)
			if st.Sport then
				lack("Kotfluegel", Vector3.new(0.7, 3.1, 3.1), CFrame.new(s * (W / 2 - 0.2), -0.5, z)).Shape = Enum.PartType.Cylinder
			end
			P("Radkasten", Vector3.new(0.12, 2.75, 2.75), CFrame.new(s * (W / 2 + (st.Sport and 0.17 or 0.01)), -0.5, z), Color3.fromRGB(12, 12, 14), nil, { Shape = Enum.PartType.Cylinder })
			local cf = CFrame.new(x, -0.5, z)
			local wheel = { Index = idx, CFrame = cf, Front = z < 0, Parts = {} }
			table.insert(wheels, wheel)
			local function wp(p)
				table.insert(wheel.Parts, p)
				return p
			end
			wp(P("Reifen", Vector3.new(tireW, 2.4, 2.4), cf, TIRE, Enum.Material.Rubber, { Shape = Enum.PartType.Cylinder }))
			wp(P("Felge", Vector3.new(tireW + 0.06, 1.65, 1.65), cf, rimColor, Enum.Material.Metal, { Shape = Enum.PartType.Cylinder, Reflectance = 0.25 }))
			for k = 0, 2 do
				wp(P("Speiche", Vector3.new(tireW + 0.08, 1.55, 0.22), cf * CFrame.Angles(k * math.pi / 3, 0, 0), Color3.fromRGB(70, 72, 78), Enum.Material.Metal))
			end
			wp(P("Nabe", Vector3.new(tireW + 0.12, 0.5, 0.5), cf, Color3.fromRGB(60, 60, 65), Enum.Material.Metal, { Shape = Enum.PartType.Cylinder }))
			if st.Sport then
				wp(P("Bremssattel", Vector3.new(tireW - 0.1, 0.5, 0.7), cf * CFrame.new(0, 0.45, 0.35), Color3.fromRGB(220, 30, 30)))
			end
		end
	end

	-- Unterbodenbeleuchtung (Garage)
	if def.Underglow then
		local glow = P("Unterboden", Vector3.new(W - 1.2, 0.08, L - 3), CFrame.new(0, bottom - 0.05, 0), def.Underglow, Enum.Material.Neon)
		Util.light(glow, "SurfaceLight", { Face = Enum.NormalId.Bottom, Range = 10, Brightness = 3, Angle = 170, Color = def.Underglow })
	end

	return {
		Lights = headlights,
		Wheels = wheels,
		Steering = steering,
		SeatCF = CFrame.new(-1.3, 0, seatZ),
		RoofInner = roofTop - 0.18,
		Belt = belt,
		Bottom = bottom,
		Style = st,
	}
end

-- Schweißt alle Teile an "root". Räder hängen über Motor6D an root.
local function assemble(m, root, info, extraSkip)
	local skip = extraSkip or {}
	skip[root] = true
	for _, wheel in ipairs(info.Wheels) do
		local hub = part({
			Name = "Radnabe",
			Size = Vector3.new(0.4, 0.4, 0.4),
			CFrame = wheel.CFrame,
			Transparency = 1,
			CanCollide = false,
			Parent = m,
		})
		hub.Anchored = false
		hub.Massless = true
		for _, wpart in ipairs(wheel.Parts) do
			wpart.Anchored = false
			wpart.Massless = true
			local w = Instance.new("WeldConstraint")
			w.Part0 = hub
			w.Part1 = wpart
			w.Parent = wpart
			skip[wpart] = true
		end
		local motor = Instance.new("Motor6D")
		motor.Name = (wheel.Front and "RadVorne" or "RadHinten") .. wheel.Index
		motor.Part0 = root
		motor.Part1 = hub
		motor.C0 = root.CFrame:Inverse() * hub.CFrame
		motor.C1 = CFrame.new()
		motor:SetAttribute("Front", wheel.Front)
		motor.Parent = root
		skip[hub] = true
	end
	if info.Steering then
		local sw = info.Steering
		sw.Anchored = false
		sw.Massless = true
		local motor = Instance.new("Motor6D")
		motor.Name = "LenkradMotor"
		motor.Part0 = root
		motor.Part1 = sw
		motor.C0 = root.CFrame:Inverse() * sw.CFrame
		motor.C1 = CFrame.new()
		motor.Parent = root
		skip[sw] = true
	end
	for _, d in ipairs(m:GetDescendants()) do
		if d:IsA("BasePart") and not skip[d] then
			d.Anchored = false
			d.Massless = true
			local w = Instance.new("WeldConstraint")
			w.Part0 = root
			w.Part1 = d
			w.Parent = d
		end
	end
end

-- Verankertes Auto (Werkstatt-Kunden, Verkehr, geparkte Autos).
-- Pivot = Karosseriemitte. Bewegen mit model:PivotTo(...).
function Cars.MakeShowCar(def)
	local m = Instance.new("Model")
	m.Name = def.Name
	local info = build(def, m, false)
	local st = info.Style
	local root = part({
		Name = "Wurzel",
		Size = Vector3.new(1, 1, 1),
		CFrame = CFrame.new(),
		Transparency = 1,
		CanCollide = false,
		Parent = m,
	})
	-- Unsichtbarer Block, damit niemand durch das stehende Auto läuft.
	-- Wird nur eingeschaltet, solange das Auto steht.
	part({
		Name = "Kollision",
		Size = Vector3.new(st.W, 2.2, st.L),
		CFrame = CFrame.new(0, 0, 0),
		Transparency = 1,
		CanCollide = false,
		Parent = m,
	})
	assemble(m, root, info)
	root.Anchored = true
	m.PrimaryPart = root
	pcall(function()
		m.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
	end)
	m:SetAttribute("SeatX", info.SeatCF.X)
	m:SetAttribute("SeatZ", info.SeatCF.Z)
	m:SetAttribute("RoofInner", info.RoofInner)
	m:SetAttribute("Belt", info.Belt)
	m:SetAttribute("Bottom", info.Bottom)
	CollectionService:AddTag(m, Cars.TAG)
	return m
end

-- Fahrbares Auto mit Dach. Pivot = Fahrgestell (CHASSIS_HEIGHT über Boden).
-- Der Spieler wird beim Fahren ausgeblendet; am Steuer sitzt eine passende
-- Kopie seines Avatars (siehe GameServer / Npc.SeatInCar).
-- Gelenkt wird vom Client (DriveClient) über "Antrieb" und "Lenkung".
function Cars.MakeDrivable(def)
	local m = Instance.new("Model")
	m.Name = def.Name
	local info = build(def, m, false)
	local st = info.Style

	local slippery = PhysicalProperties.new(0.7, 0, 0, 100, 1)
	local chassis = part({
		Name = "Fahrgestell",
		Size = Vector3.new(st.W - 0.4, 1, st.L - 0.6),
		CFrame = CFrame.new(0, Cars.CHASSIS_HEIGHT - Cars.BODY_HEIGHT, 0),
		Transparency = 1,
		CanCollide = true,
		CustomPhysicalProperties = slippery,
		Parent = m,
	})
	-- Kugeln als Bodenkontakt: rollen über kleine Kanten
	for _, z in ipairs({ -st.Axle, st.Axle }) do
		for _, s in ipairs({ -1, 1 }) do
			part({
				Name = "Kontakt",
				Shape = Enum.PartType.Ball,
				Size = Vector3.new(1.2, 1.2, 1.2),
				CFrame = CFrame.new(s * (st.W / 2 - 0.6), 0.6 - Cars.BODY_HEIGHT, z),
				Transparency = 1,
				CanCollide = true,
				CustomPhysicalProperties = slippery,
				Parent = m,
			})
		end
	end

	local seat = Instance.new("VehicleSeat")
	seat.Name = "Fahrersitz"
	seat.Size = Vector3.new(1.6, 0.4, 1.6)
	seat.CFrame = CFrame.new(info.SeatCF.X, st.Bottom + 0.35, info.SeatCF.Z + 0.3)
	seat.Transparency = 1
	seat.CanCollide = false
	seat.HeadsUpDisplay = false
	seat.MaxSpeed = 0
	seat.Torque = 0
	seat.TurnSpeed = 0
	seat.Parent = m

	for _, hl in ipairs(info.Lights) do
		Util.light(hl, "SpotLight", { Face = Enum.NormalId.Front, Range = 60, Brightness = 2, Angle = 70, Color = Color3.fromRGB(255, 245, 225) })
	end

	assemble(m, chassis, info)
	chassis.Anchored = false

	local att = Instance.new("Attachment")
	att.Name = "Mitte"
	att.Parent = chassis

	local lv = Instance.new("LinearVelocity")
	lv.Name = "Antrieb"
	lv.Attachment0 = att
	lv.RelativeTo = Enum.ActuatorRelativeTo.World
	lv.VelocityConstraintMode = Enum.VelocityConstraintMode.Plane
	lv.PrimaryTangentAxis = Vector3.xAxis
	lv.SecondaryTangentAxis = Vector3.zAxis
	lv.PlaneVelocity = Vector2.zero
	lv.MaxForce = 12000
	lv.Parent = chassis

	local av = Instance.new("AngularVelocity")
	av.Name = "Lenkung"
	av.Attachment0 = att
	av.RelativeTo = Enum.ActuatorRelativeTo.World
	av.AngularVelocity = Vector3.zero
	av.MaxTorque = 60000
	av.Parent = chassis

	m.PrimaryPart = chassis
	m:SetAttribute("SeatX", info.SeatCF.X)
	m:SetAttribute("SeatZ", info.SeatCF.Z)
	m:SetAttribute("RoofInner", info.RoofInner)
	m:SetAttribute("Bottom", info.Bottom)
	m:SetAttribute("RootOffsetY", Cars.CHASSIS_HEIGHT - Cars.BODY_HEIGHT)
	pcall(function()
		m.ModelStreamingMode = Enum.ModelStreamingMode.Atomic
	end)
	CollectionService:AddTag(m, Cars.TAG)
	return m, seat
end

-- Licht-Helfer (nur optisch, lokal auf dem Client)
local BRAKE_ON = Color3.fromRGB(255, 35, 35)
local BRAKE_OFF = Color3.fromRGB(130, 8, 12)
local BLINK_ON = Color3.fromRGB(255, 170, 20)
local BLINK_OFF = Color3.fromRGB(110, 65, 10)

function Cars.LightParts(car)
	local l = { Brake = {}, Left = {}, Right = {} }
	for _, d in ipairs(car:GetDescendants()) do
		if d:IsA("BasePart") then
			if d.Name == "Ruecklicht" or d.Name == "Rueckleuchtenband" or d.Name == "Bremslicht" then
				table.insert(l.Brake, d)
			elseif d.Name == "BlinkerVL" or d.Name == "BlinkerHL" then
				table.insert(l.Left, d)
			elseif d.Name == "BlinkerVR" or d.Name == "BlinkerHR" then
				table.insert(l.Right, d)
			end
		end
	end
	return l
end

function Cars.SetLights(l, braking, blink, now)
	if l.BrakeState ~= braking then
		l.BrakeState = braking
		for _, p in ipairs(l.Brake) do
			p.Color = braking and BRAKE_ON or BRAKE_OFF
		end
	end
	local on = blink ~= 0 and (math.floor(now * 2.5) % 2 == 0)
	local state = on and blink or 0
	if l.BlinkState ~= state then
		l.BlinkState = state
		for _, p in ipairs(l.Left) do
			local lit = state < 0
			p.Color = lit and BLINK_ON or BLINK_OFF
			p.Material = lit and Enum.Material.Neon or Enum.Material.SmoothPlastic
		end
		for _, p in ipairs(l.Right) do
			local lit = state > 0
			p.Color = lit and BLINK_ON or BLINK_OFF
			p.Material = lit and Enum.Material.Neon or Enum.Material.SmoothPlastic
		end
	end
end

return Cars
