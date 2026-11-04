-- Die Spielwelt: Gelände, Licht, Straßen, Teststrecke, Bäume, Gebäude
-- ModuleScript "World" in ServerScriptService
--
-- Übersicht (von oben, Norden = -Z):
--   z = -750 … -150 : Teststrecke (Oval) mit Tribüne
--   z =  -45 …   45 : Werkstätten der Spieler (an der Werkstattstraße)
--   z =   50        : Werkstattstraße (Ost-West)
--   z =   80 …  200 : Läden und Gebäude
--   außen herum     : Landstraße als großer Rundkurs, See im Südosten, Berge am Rand

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Lighting = game:GetService("Lighting")

local Config = require(ReplicatedStorage:WaitForChild("Config"))
local Util = require(ReplicatedStorage:WaitForChild("Util"))
local Cars = require(ReplicatedStorage:WaitForChild("Cars"))
local part = Util.part

local World = {}

World.ROAD_Z = 50
World.PLOT_SPACING = 100
World.ROAD_TOP = 0.05 -- Oberkante der Straßen

local T = Config.Track
local SOUTH_Z = T.CenterZ + T.Radius
local NORTH_Z = T.CenterZ - T.Radius

local ASPHALT = Color3.fromRGB(52, 53, 58)

local folder

------------------------------------------------------------------------
-- Licht und Atmosphäre
------------------------------------------------------------------------
local function setProps(inst, props)
	for k, v in pairs(props) do
		local ok, err = pcall(function()
			inst[k] = v
		end)
		if not ok then
			warn("[World] " .. inst.ClassName .. "." .. k .. ": " .. tostring(err))
		end
	end
end

local function buildLighting()
	for _, child in ipairs(Lighting:GetChildren()) do
		if child:IsA("PostEffect") or child:IsA("Atmosphere") or child:IsA("Sky") then
			child:Destroy()
		end
	end
	setProps(Lighting, {
		ClockTime = 14,
		GeographicLatitude = 45,
		Brightness = 2.6,
		Ambient = Color3.fromRGB(45, 45, 52),
		OutdoorAmbient = Color3.fromRGB(125, 125, 135),
		EnvironmentDiffuseScale = 1,
		EnvironmentSpecularScale = 1,
		GlobalShadows = true,
		ShadowSoftness = 0.15,
		ExposureCompensation = 0.1,
	})

	local atmo = Instance.new("Atmosphere")
	setProps(atmo, {
		Density = 0.28,
		Offset = 0.2,
		Color = Color3.fromRGB(199, 205, 215),
		Decay = Color3.fromRGB(110, 118, 132),
		Glare = 0.35,
		Haze = 1.4,
	})
	atmo.Parent = Lighting

	local sky = Instance.new("Sky")
	setProps(sky, { SunAngularSize = 14, MoonAngularSize = 9, StarCount = 3000 })
	sky.Parent = Lighting

	local bloom = Instance.new("BloomEffect")
	setProps(bloom, { Intensity = 0.45, Size = 24, Threshold = 1.3 })
	bloom.Parent = Lighting

	local cc = Instance.new("ColorCorrectionEffect")
	setProps(cc, { Brightness = 0.02, Contrast = 0.1, Saturation = 0.15, TintColor = Color3.fromRGB(255, 250, 244) })
	cc.Parent = Lighting

	local rays = Instance.new("SunRaysEffect")
	setProps(rays, { Intensity = 0.05, Spread = 0.6 })
	rays.Parent = Lighting

	local clouds = Instance.new("Clouds")
	setProps(clouds, { Cover = 0.55, Density = 0.6, Color = Color3.fromRGB(245, 245, 250) })
	clouds.Parent = workspace.Terrain
end

------------------------------------------------------------------------
-- Gelände (Terrain)
------------------------------------------------------------------------
local function buildTerrain()
	local terrain = workspace.Terrain
	pcall(function()
		terrain.Decoration = false -- keine Grashalme, die durch Böden wachsen
	end)
	-- natürlichere Farben
	pcall(function()
		terrain:SetMaterialColor(Enum.Material.Grass, Color3.fromRGB(92, 132, 64))
		terrain:SetMaterialColor(Enum.Material.LeafyGrass, Color3.fromRGB(72, 110, 50))
		terrain:SetMaterialColor(Enum.Material.Ground, Color3.fromRGB(110, 90, 68))
		terrain:SetMaterialColor(Enum.Material.Rock, Color3.fromRGB(118, 116, 112))
		terrain:SetMaterialColor(Enum.Material.Sand, Color3.fromRGB(214, 198, 152))
	end)
	-- Grundfläche, Oberkante y = 0
	terrain:FillBlock(CFrame.new(0, -6, 0), Vector3.new(2800, 12, 2800), Enum.Material.Grass)

	-- Berge ringsum
	local rng = Random.new(7)
	for i = 0, 39 do
		local a = i / 40 * math.pi * 2
		local r = 1280 + rng:NextNumber(-30, 60)
		local radius = rng:NextNumber(110, 190)
		local mat = (i % 3 == 0) and Enum.Material.Rock or Enum.Material.Grass
		terrain:FillBall(Vector3.new(math.cos(a) * r, -radius * 0.25, math.sin(a) * r), radius, mat)
		if mat == Enum.Material.Rock and radius > 150 then
			terrain:FillBall(Vector3.new(math.cos(a) * (r + 30), radius * 0.45, math.sin(a) * (r + 30)), radius * 0.45, Enum.Material.Snow)
		end
	end

	-- See mit Sandstrand im Südosten
	local lake = CFrame.new(650, 0, 430)
	terrain:FillBlock(lake * CFrame.new(0, -4, 0), Vector3.new(300, 8, 240), Enum.Material.Sand)
	terrain:FillBlock(lake * CFrame.new(0, -6, 0), Vector3.new(250, 12, 190), Enum.Material.Air)
	terrain:FillBlock(lake * CFrame.new(0, -8, 0), Vector3.new(250, 12, 190), Enum.Material.Water)
	terrain:FillBlock(lake * CFrame.new(0, -15, 0), Vector3.new(250, 2, 190), Enum.Material.Sand)
end

------------------------------------------------------------------------
-- Befestigte Flächen
------------------------------------------------------------------------
-- Entfernt das Gelände unter einer Fläche und setzt eine 4 Studs dicke Platte
-- ein. cf liegt auf Bodenhöhe (y = 0), top ist die Oberkante der Platte.
function World.Slab(cf, sizeX, sizeZ, top, color, material, name, parent)
	workspace.Terrain:FillBlock(cf * CFrame.new(0, 2, 0), Vector3.new(sizeX, 12, sizeZ), Enum.Material.Air)
	return part({
		Name = name or "Platte",
		Size = Vector3.new(sizeX, 4, sizeZ),
		CFrame = cf * CFrame.new(0, top - 2, 0),
		Color = color,
		Material = material,
		Parent = parent or folder,
	})
end

------------------------------------------------------------------------
-- Straßen
------------------------------------------------------------------------
local roadCount = 0

-- Gerades Straßenstück von a nach b (Vector3, y egal)
local function road(a, b, width, dashes, color)
	roadCount += 1
	local top = World.ROAD_TOP + roadCount * 0.004 -- gegen Flimmern bei Überlappung
	local pa = Vector3.new(a.X, 0, a.Z)
	local pb = Vector3.new(b.X, 0, b.Z)
	local len = (pb - pa).Magnitude
	local mid = (pa + pb) / 2
	local cf = CFrame.lookAt(mid, pb)
	World.Slab(cf, width, len, top, color or ASPHALT, Enum.Material.Asphalt, "Strasse")
	-- Bordsteine
	for _, side in ipairs({ -1, 1 }) do
		part({
			Name = "Bordstein",
			Size = Vector3.new(0.8, 0.3, len),
			CFrame = cf * CFrame.new(side * (width / 2 + 0.4), top - 0.05, 0),
			Color = Color3.fromRGB(165, 165, 168),
			Material = Enum.Material.Concrete,
			CanCollide = false,
			Parent = folder,
		})
	end
	if dashes then
		local n = math.floor(len / 20)
		for i = 0, n - 1 do
			local z = -len / 2 + 10 + i * 20
			part({
				Name = "Markierung",
				Size = Vector3.new(0.6, 0.05, 8),
				CFrame = cf * CFrame.new(0, top + 0.02, z),
				Color = Color3.fromRGB(235, 235, 235),
				Material = Enum.Material.SmoothPlastic,
				CanCollide = false,
				Parent = folder,
			})
		end
	end
end

local function buildRoads()
	local z = World.ROAD_Z
	road(Vector3.new(-950, 0, z), Vector3.new(950, 0, z), 22, true) -- Werkstattstraße
	road(Vector3.new(0, 0, z - 11), Vector3.new(0, 0, SOUTH_Z + 14), 18, true) -- Zufahrt Teststrecke
	-- Landstraße (großer Rundkurs)
	road(Vector3.new(-700, 0, 260), Vector3.new(700, 0, 260), 20, true)
	road(Vector3.new(-700, 0, -780), Vector3.new(700, 0, -780), 20, true)
	road(Vector3.new(-700, 0, -790), Vector3.new(-700, 0, 270), 20, true)
	road(Vector3.new(700, 0, -790), Vector3.new(700, 0, 270), 20, true)
	-- Verbindung zur Tribüne / zum See
	road(Vector3.new(560, 0, 270), Vector3.new(560, 0, 300), 14, false)
end

------------------------------------------------------------------------
-- Teststrecke
------------------------------------------------------------------------
local function curb(cf, i, length)
	part({
		Name = "Curb",
		Size = Vector3.new(1.6, 0.25, length),
		CFrame = cf,
		Color = (i % 2 == 0) and Color3.fromRGB(210, 30, 30) or Color3.fromRGB(240, 240, 240),
		Material = Enum.Material.SmoothPlastic,
		Parent = folder,
	})
end

local function buildTrack()
	local top = 0.09
	local hl, r, w = T.HalfLength, T.Radius, T.Width
	local cz = T.CenterZ
	local trackColor = Color3.fromRGB(44, 45, 50)

	-- Geraden
	for _, zz in ipairs({ SOUTH_Z, NORTH_Z }) do
		World.Slab(CFrame.new(0, 0, zz), hl * 2, w, top, trackColor, Enum.Material.Asphalt, "Gerade")
		for _, side in ipairs({ -1, 1 }) do
			part({
				Name = "Randlinie",
				Size = Vector3.new(hl * 2, 0.05, 0.7),
				CFrame = CFrame.new(0, top + 0.02, zz + side * (w / 2 - 1)),
				Color = Color3.new(1, 1, 1),
				Material = Enum.Material.SmoothPlastic,
				CanCollide = false,
				Parent = folder,
			})
		end
	end

	-- Kurven (Halbkreise) aus Segmenten
	local N = 30
	for _, side in ipairs({ 1, -1 }) do
		local cx = side * hl
		local a0 = side == 1 and -math.pi / 2 or math.pi / 2
		for k = 0, N - 1 do
			local t0 = a0 + k / N * math.pi
			local t1 = a0 + (k + 1) / N * math.pi
			local p0 = Vector3.new(cx + math.cos(t0) * r, 0, cz + math.sin(t0) * r)
			local p1 = Vector3.new(cx + math.cos(t1) * r, 0, cz + math.sin(t1) * r)
			local mid = (p0 + p1) / 2
			local cf = CFrame.lookAt(mid, p1)
			local len = (p1 - p0).Magnitude
			-- Außen ist das Segment länger als innen: Länge an Außenkante anpassen
			local outerLen = len * (r + w / 2) / r + 0.4
			World.Slab(cf, w, outerLen, top - 0.001 * (k % 2), trackColor, Enum.Material.Asphalt, "Kurve")
			-- Kiesbett außen bis zur Mauer
			local radialMid = (mid - Vector3.new(cx, 0, cz)).Unit
			local gravelR = r + w / 2 + 7.5
			local gpos = Vector3.new(cx, 0, cz) + radialMid * gravelR
			World.Slab(
				CFrame.lookAt(gpos, gpos + cf.LookVector),
				12,
				len * gravelR / r + 0.6,
				0.06 - 0.001 * (k % 2),
				Color3.fromRGB(196, 180, 150),
				Enum.Material.Pebble,
				"Kiesbett"
			)
			-- Curbs innen und außen
			local radial = (mid - Vector3.new(cx, 0, cz)).Unit
			for _, off in ipairs({ r - w / 2 - 0.8, r + w / 2 + 0.8 }) do
				local pos = Vector3.new(cx, 0, cz) + radial * off
				local scale = off / r
				local ccf = CFrame.lookAt(pos, pos + cf.LookVector) * CFrame.new(0, 0.12, 0)
				for j = 0, 1 do
					curb(ccf * CFrame.new(0, 0, (j - 0.5) * len * scale / 2), k * 2 + j, len * scale / 2 + 0.05)
				end
			end
			-- Betonmauer außen
			local wallPos = Vector3.new(cx, 0, cz) + radial * (r + w / 2 + 14)
			part({
				Name = "Mauer",
				Size = Vector3.new(1.5, 3, len * (r + w / 2 + 14) / r + 0.3),
				CFrame = CFrame.lookAt(wallPos, wallPos + cf.LookVector) * CFrame.new(0, 1.5, 0),
				Color = (k % 2 == 0) and Color3.fromRGB(230, 230, 230) or Color3.fromRGB(200, 40, 40),
				Material = Enum.Material.Concrete,
				Parent = folder,
			})
		end
	end

	-- Start/Ziel: Schachbrett und Portal
	for row = 0, 1 do
		for i = 0, w / 2 - 1 do
			part({
				Name = "Zielinie",
				Size = Vector3.new(2, 0.05, 2),
				CFrame = CFrame.new(-1 + row * 2, top + 0.03, SOUTH_Z - w / 2 + 1 + i * 2),
				Color = ((i + row) % 2 == 0) and Color3.new(1, 1, 1) or Color3.new(0.05, 0.05, 0.05),
				Material = Enum.Material.SmoothPlastic,
				CanCollide = false,
				Parent = folder,
			})
		end
	end
	for _, side in ipairs({ -1, 1 }) do
		part({
			Name = "Portal",
			Size = Vector3.new(1.5, 18, 1.5),
			CFrame = CFrame.new(0, 9, SOUTH_Z + side * (w / 2 + 2)),
			Color = Color3.fromRGB(30, 30, 34),
			Material = Enum.Material.Metal,
			Parent = folder,
		})
	end
	local beam = part({
		Name = "PortalSchild",
		Size = Vector3.new(1.5, 4, w + 6),
		CFrame = CFrame.new(0, 17, SOUTH_Z),
		Color = Color3.fromRGB(20, 20, 24),
		Parent = folder,
	})
	Util.textGui(beam, Enum.NormalId.Left, "🏁 TESTSTRECKE 🏁", Color3.fromRGB(255, 140, 0), Color3.fromRGB(20, 20, 24))
	Util.textGui(beam, Enum.NormalId.Right, "🏁 TESTSTRECKE 🏁", Color3.fromRGB(255, 140, 0), Color3.fromRGB(20, 20, 24))

	-- Tribüne innerhalb des Ovals, mit Blick auf die Start-Ziel-Gerade
	local standZ = SOUTH_Z - w / 2 - 22
	for tier = 0, 5 do
		part({
			Name = "Tribuene",
			Size = Vector3.new(120, 1.5 + tier * 1.5, 4),
			CFrame = CFrame.new(0, (1.5 + tier * 1.5) / 2, standZ - tier * 4),
			Color = (tier % 2 == 0) and Color3.fromRGB(60, 90, 160) or Color3.fromRGB(50, 75, 140),
			Material = Enum.Material.SmoothPlastic,
			Parent = folder,
		})
	end
	part({
		Name = "TribuenenDach",
		Size = Vector3.new(124, 1, 30),
		CFrame = CFrame.new(0, 18, standZ - 10) * CFrame.Angles(math.rad(-8), 0, 0),
		Color = Color3.fromRGB(235, 235, 240),
		Material = Enum.Material.Metal,
		Parent = folder,
	})
	for _, x in ipairs({ -58, 0, 58 }) do
		part({
			Name = "DachStuetze",
			Size = Vector3.new(1.2, 18, 1.2),
			CFrame = CFrame.new(x, 9, standZ - 22),
			Color = Color3.fromRGB(80, 80, 85),
			Material = Enum.Material.Metal,
			Parent = folder,
		})
	end

	-- Flutlichtmasten
	for _, p in ipairs({ Vector3.new(-150, 0, SOUTH_Z + 30), Vector3.new(150, 0, SOUTH_Z + 30), Vector3.new(-150, 0, NORTH_Z - 30), Vector3.new(150, 0, NORTH_Z - 30) }) do
		part({ Name = "Mast", Size = Vector3.new(1.5, 40, 1.5), CFrame = CFrame.new(p + Vector3.new(0, 20, 0)), Color = Color3.fromRGB(90, 90, 95), Material = Enum.Material.Metal, Parent = folder })
		local head = part({
			Name = "Flutlicht",
			Size = Vector3.new(8, 3, 2),
			CFrame = CFrame.lookAt(p + Vector3.new(0, 40, 0), Vector3.new(p.X, 0, T.CenterZ)),
			Color = Color3.fromRGB(255, 250, 235),
			Material = Enum.Material.Neon,
			Parent = folder,
		})
		Util.light(head, "SpotLight", { Face = Enum.NormalId.Front, Range = 60, Brightness = 3, Angle = 90 })
	end
end

------------------------------------------------------------------------
-- Fahrerlager an der Start-Ziel-Geraden
------------------------------------------------------------------------
local function buildPaddock()
	local z0 = SOUTH_Z + T.Width / 2 - 1 -- direkt an der Strecke
	local depth = 70
	local cz = z0 + depth / 2
	World.Slab(CFrame.new(0, 0, cz), 380, depth, 0.07, Color3.fromRGB(60, 61, 66), Enum.Material.Asphalt, "Fahrerlager")
	-- Boxenmauer mit Lücke für die Zufahrt
	for _, side in ipairs({ -1, 1 }) do
		part({
			Name = "Boxenmauer",
			Size = Vector3.new(170, 1.6, 1),
			CFrame = CFrame.new(side * 105, 0.85, z0 + 2),
			Color = Color3.fromRGB(235, 235, 235),
			Material = Enum.Material.Concrete,
			Parent = folder,
		})
	end
	-- Parkbuchten
	for x = -176, 176, 10 do
		if math.abs(x) > 24 then
			part({
				Name = "Parklinie",
				Size = Vector3.new(0.4, 0.05, 14),
				CFrame = CFrame.new(x, 0.1, z0 + depth - 9),
				Color = Color3.new(1, 1, 1),
				Material = Enum.Material.SmoothPlastic,
				CanCollide = false,
				Parent = folder,
			})
		end
	end
	-- Boxengebäude
	local box = part({
		Name = "Boxengebaeude",
		Size = Vector3.new(120, 12, 16),
		CFrame = CFrame.new(-120, 6, z0 + depth + 8),
		Color = Color3.fromRGB(230, 232, 236),
		Material = Enum.Material.SmoothPlastic,
		Parent = folder,
	})
	Util.textGui(box, Enum.NormalId.Front, "BOXEN · PIT LANE", Color3.fromRGB(255, 140, 0), Color3.fromRGB(25, 25, 30))
	for i = 0, 4 do
		part({
			Name = "Boxentor",
			Size = Vector3.new(18, 8, 0.3),
			CFrame = CFrame.new(-168 + i * 24, 4.2, z0 + depth - 0.1),
			Color = Color3.fromRGB(40, 42, 48),
			Material = Enum.Material.Metal,
			Parent = folder,
		})
	end
end

------------------------------------------------------------------------
-- Straßenlaternen
------------------------------------------------------------------------
local function lamp(pos, facing)
	local pole = Color3.fromRGB(45, 48, 52)
	part({ Name = "Mast", Shape = Enum.PartType.Cylinder, Size = Vector3.new(14, 0.6, 0.6), CFrame = CFrame.new(pos + Vector3.new(0, 7, 0)) * CFrame.Angles(0, 0, math.rad(90)), Color = pole, Material = Enum.Material.Metal, Parent = folder })
	part({ Name = "Arm", Size = Vector3.new(0.35, 0.35, 4), CFrame = CFrame.lookAt(pos + Vector3.new(0, 14, 0), pos + Vector3.new(0, 14, 0) + facing) * CFrame.new(0, 0, -2), Color = pole, Material = Enum.Material.Metal, Parent = folder })
	local head = part({
		Name = "Leuchte",
		Size = Vector3.new(1.6, 0.35, 2.4),
		CFrame = CFrame.lookAt(pos + Vector3.new(0, 13.8, 0) + facing * 4, pos + Vector3.new(0, 13.8, 0) + facing * 5),
		Color = Color3.fromRGB(255, 236, 200),
		Material = Enum.Material.Neon,
		Parent = folder,
	})
	Util.light(head, "SpotLight", { Face = Enum.NormalId.Bottom, Range = 30, Brightness = 2.2, Angle = 120, Color = Color3.fromRGB(255, 225, 180) })
end

local function buildLamps()
	for x = -900, 900, 60 do
		lamp(Vector3.new(x, 0.25, World.ROAD_Z + 19.4), -Vector3.zAxis)
	end
	for z = SOUTH_Z + 40, -60, 50 do
		lamp(Vector3.new(14, 0, z), -Vector3.xAxis)
	end
end

------------------------------------------------------------------------
-- Gebäude an der Werkstattstraße (Südseite)
------------------------------------------------------------------------
local SHOPS = {
	{ "Reifen Express", Color3.fromRGB(40, 40, 45), Color3.fromRGB(255, 200, 0) },
	{ "Tankstelle", Color3.fromRGB(230, 230, 235), Color3.fromRGB(220, 30, 30) },
	{ "Lackiererei Glanz", Color3.fromRGB(70, 90, 120), Color3.fromRGB(120, 220, 255) },
	{ "Autohaus Nord", Color3.fromRGB(235, 235, 240), Color3.fromRGB(30, 90, 200) },
	{ "Café Ladedruck", Color3.fromRGB(120, 80, 60), Color3.fromRGB(255, 220, 160) },
	{ "Teile-Lager", Color3.fromRGB(150, 150, 155), Color3.fromRGB(255, 140, 0) },
	{ "Waschanlage", Color3.fromRGB(60, 140, 200), Color3.fromRGB(255, 255, 255) },
	{ "Felgen-Shop", Color3.fromRGB(30, 30, 35), Color3.fromRGB(200, 200, 210) },
	{ "Motorsport Halle", Color3.fromRGB(180, 30, 30), Color3.fromRGB(255, 255, 255) },
	{ "Bürogebäude", Color3.fromRGB(190, 195, 200), Color3.fromRGB(80, 200, 255) },
}

local function building(x, width, depth, height, name, wallColor, signColor, rng)
	local zFront = World.ROAD_Z + 30
	local cz = zFront + depth / 2
	local wallMat = rng:NextNumber() < 0.4 and Enum.Material.Brick or Enum.Material.Concrete
	part({ Name = name, Size = Vector3.new(width, height, depth), CFrame = CFrame.new(x, height / 2, cz), Color = wallColor, Material = wallMat, Parent = folder })
	part({ Name = "Dachkante", Size = Vector3.new(width + 1, 1, depth + 1), CFrame = CFrame.new(x, height + 0.5, cz), Color = Color3.fromRGB(60, 60, 65), Material = Enum.Material.Concrete, Parent = folder })
	-- Fenster an der Vorderseite (zeigt zur Straße, -Z)
	local cols = math.floor((width - 6) / 7)
	local rows = math.floor((height - 12) / 8)
	for r = 0, rows - 1 do
		for c = 0, cols - 1 do
			local wx = x - (cols - 1) * 3.5 + c * 7
			local wy = 12 + r * 8 + 2
			local lit = rng:NextNumber() < 0.35
			part({
				Name = "Fenster",
				Size = Vector3.new(4.5, 4.5, 0.3),
				CFrame = CFrame.new(wx, wy, zFront - 0.1),
				Color = lit and Color3.fromRGB(255, 225, 160) or Color3.fromRGB(35, 50, 70),
				Material = lit and Enum.Material.Neon or Enum.Material.Glass,
				Reflectance = lit and 0 or 0.3,
				Parent = folder,
			})
		end
	end
	-- Eingang / Schaufenster unten
	part({ Name = "Schaufenster", Size = Vector3.new(width * 0.6, 6, 0.3), CFrame = CFrame.new(x, 3.5, zFront - 0.1), Color = Color3.fromRGB(40, 60, 80), Material = Enum.Material.Glass, Transparency = 0.2, Reflectance = 0.3, Parent = folder })
	local sign = part({ Name = "Ladenschild", Size = Vector3.new(math.min(width - 4, 40), 4, 0.6), CFrame = CFrame.new(x, 8.5, zFront - 0.4), Color = Color3.fromRGB(15, 15, 18), Parent = folder })
	Util.textGui(sign, Enum.NormalId.Front, name, signColor, Color3.fromRGB(15, 15, 18))
	-- Gehweg
	World.Slab(CFrame.new(x, 0, zFront - 5), width + 10, 10, 0.4, Color3.fromRGB(175, 175, 178), Enum.Material.Pavement, "Gehweg")
end

local function buildTown()
	local rng = Random.new(3)
	local x = -560
	local i = 0
	while x < 560 do
		local width = rng:NextInteger(40, 64)
		local cx = x + width / 2
		if math.abs(cx) > width / 2 + 30 then -- Platz für den Spawn in der Mitte lassen
			i += 1
			local shop = SHOPS[(i - 1) % #SHOPS + 1]
			building(cx, width, rng:NextInteger(40, 70), rng:NextInteger(22, 46), shop[1], shop[2], shop[3], rng)
		end
		x += width + rng:NextInteger(14, 30)
	end
end

------------------------------------------------------------------------
-- Bäume
------------------------------------------------------------------------
local BLOCKED = {
	-- {minX, maxX, minZ, maxZ}
	{ -960, 960, 20, 80 }, -- Werkstattstraße + Laternen
	{ -330, 330, -50, 45 }, -- Werkstätten
	{ -25, 25, SOUTH_Z, 60 }, -- Zufahrt
	{ -T.HalfLength - T.Radius - 40, T.HalfLength + T.Radius + 40, NORTH_Z - 50, SOUTH_Z + 95 }, -- Teststrecke + Fahrerlager
	{ -600, 600, 75, 200 }, -- Gebäude
	{ -720, 720, 245, 275 }, -- Landstraße Süd
	{ -720, 720, -795, -765 },
	{ -715, -685, -795, 275 },
	{ 685, 715, -795, 275 },
	{ 480, 820, 290, 570 }, -- See
	{ -1010, -750, -310, 110 }, -- Feld West
	{ 750, 1010, -510, -90 }, -- Feld Ost
}

local function isFree(x, z)
	for _, b in ipairs(BLOCKED) do
		if x > b[1] and x < b[2] and z > b[3] and z < b[4] then
			return false
		end
	end
	return math.sqrt(x * x + z * z) < 1020
end

local rayParams = RaycastParams.new()
rayParams.FilterType = Enum.RaycastFilterType.Include
rayParams.FilterDescendantsInstances = { workspace.Terrain }

local function groundY(x, z)
	local hit = workspace:Raycast(Vector3.new(x, 250, z), Vector3.new(0, -500, 0), rayParams)
	return hit and hit.Position.Y or 0
end
World.GroundY = groundY

local function tree(pos, rng)
	local trunkH = rng:NextNumber(7, 11)
	part({
		Name = "Stamm",
		Shape = Enum.PartType.Cylinder,
		Size = Vector3.new(trunkH, 1.4, 1.4),
		CFrame = CFrame.new(pos + Vector3.new(0, trunkH / 2, 0)) * CFrame.Angles(0, 0, math.rad(90)),
		Color = Color3.fromRGB(95, 70, 50),
		Material = Enum.Material.Wood,
		Parent = folder,
	})
	if rng:NextNumber() < 0.35 then
		-- Nadelbaum: gestapelte Scheiben
		for i = 0, 3 do
			local d = 11 - i * 2.5
			part({
				Name = "Nadeln",
				Shape = Enum.PartType.Cylinder,
				Size = Vector3.new(2.6, d, d),
				CFrame = CFrame.new(pos + Vector3.new(0, trunkH - 2 + i * 2.6, 0)) * CFrame.Angles(0, 0, math.rad(90)),
				Color = Color3.fromRGB(35, 80 + i * 5, 45),
				Material = Enum.Material.Grass,
				CanCollide = false,
				Parent = folder,
			})
		end
	else
		local g = rng:NextInteger(95, 140)
		for _ = 1, 3 do
			local s = rng:NextNumber(7, 11)
			part({
				Name = "Krone",
				Shape = Enum.PartType.Ball,
				Size = Vector3.new(s, s, s),
				CFrame = CFrame.new(pos + Vector3.new(rng:NextNumber(-2, 2), trunkH + rng:NextNumber(0, 3), rng:NextNumber(-2, 2))),
				Color = Color3.fromRGB(55, g, 50),
				Material = Enum.Material.Grass,
				CanCollide = false,
				Parent = folder,
			})
		end
	end
end

local function buildTrees()
	local rng = Random.new(42)
	local placed = 0
	local tries = 0
	while placed < 380 and tries < 5000 do
		tries += 1
		local x = rng:NextNumber(-1020, 1020)
		local z = rng:NextNumber(-1020, 1020)
		if isFree(x, z) then
			tree(Vector3.new(x, groundY(x, z) - 0.3, z), rng)
			placed += 1
		end
	end
	-- Allee entlang der Zufahrt zur Teststrecke
	for z = SOUTH_Z + 110, -60, 40 do
		tree(Vector3.new(-22, 0, z), rng)
		tree(Vector3.new(26, 0, z + 20), rng)
	end
end


------------------------------------------------------------------------
-- Natur: Hügel, Wiesen, Felder, Büsche, Felsen, Blumen
------------------------------------------------------------------------

local function areaFree(x, z, r)
	if not isFree(x, z) then
		return false
	end
	for k = 0, 7 do
		local a = k / 8 * math.pi * 2
		if not isFree(x + math.cos(a) * r, z + math.sin(a) * r) then
			return false
		end
	end
	return true
end

local function region(x0, z0, x1, z1)
	return Region3.new(Vector3.new(math.min(x0, x1), -12, math.min(z0, z1)), Vector3.new(math.max(x0, x1), 60, math.max(z0, z1))):ExpandToGrid(4)
end

local function buildHills()
	local terrain = workspace.Terrain
	local rng = Random.new(19)
	local made, tries = 0, 0
	while made < 34 and tries < 800 do
		tries += 1
		local r = rng:NextNumber(28, 70)
		local x, z = rng:NextNumber(-1000, 1000), rng:NextNumber(-1000, 1000)
		if areaFree(x, z, r + 12) then
			terrain:FillBall(Vector3.new(x, -r * 0.78, z), r, Enum.Material.Grass)
			made += 1
		end
	end
	-- Wiesenflecken und Erdstellen für ein natürlicheres Bild
	for _ = 1, 70 do
		local x, z = rng:NextNumber(-1000, 1000), rng:NextNumber(-1000, 1000)
		local w, d = rng:NextNumber(16, 70), rng:NextNumber(16, 70)
		pcall(function()
			terrain:ReplaceMaterial(region(x, z, x + w, z + d), 4, Enum.Material.Grass, Enum.Material.LeafyGrass)
		end)
	end
	for _ = 1, 14 do
		local x, z = rng:NextNumber(-1000, 1000), rng:NextNumber(-1000, 1000)
		local w = rng:NextNumber(8, 20)
		pcall(function()
			terrain:ReplaceMaterial(region(x, z, x + w, z + w), 4, Enum.Material.Grass, Enum.Material.Ground)
		end)
	end
end

local function fence(a, b)
	local dir = b - a
	local len = dir.Magnitude
	local n = math.floor(len / 8)
	local wood = Color3.fromRGB(120, 90, 60)
	for i = 0, n do
		local p = a + dir * (i / math.max(n, 1))
		part({ Name = "Zaunpfahl", Size = Vector3.new(0.5, 3.2, 0.5), CFrame = CFrame.new(p.X, 1.4, p.Z), Color = wood, Material = Enum.Material.Wood, Parent = folder })
	end
	local mid = (a + b) / 2
	for _, h in ipairs({ 1.2, 2.4 }) do
		part({
			Name = "Zaunlatte",
			Size = Vector3.new(0.25, 0.35, len),
			CFrame = CFrame.lookAt(Vector3.new(mid.X, h, mid.Z), Vector3.new(b.X, h, b.Z)),
			Color = wood,
			Material = Enum.Material.WoodPlanks,
			Parent = folder,
		})
	end
end

local function field(x0, z0, x1, z1)
	local terrain = workspace.Terrain
	-- Furchen: abwechselnd Erde und Pflanzenreihen
	local x = x0
	local row = 0
	while x < x1 do
		pcall(function()
			terrain:ReplaceMaterial(region(x, z0, x + 4, z1), 4, row % 2 == 0 and Enum.Material.Grass or Enum.Material.LeafyGrass, Enum.Material.Ground)
		end)
		row += 1
		x += 8
	end
	local c = { Vector3.new(x0, 0, z0), Vector3.new(x1, 0, z0), Vector3.new(x1, 0, z1), Vector3.new(x0, 0, z1) }
	for i = 1, 4 do
		fence(c[i], c[i % 4 + 1])
	end
end

local function buildNatureDetails()
	local rng = Random.new(23)
	field(-1000, -300, -760, 100)
	field(760, -500, 1000, -100)

	-- Büsche
	local placed, tries = 0, 0
	while placed < 260 and tries < 4000 do
		tries += 1
		local x, z = rng:NextNumber(-1000, 1000), rng:NextNumber(-1000, 1000)
		if isFree(x, z) then
			local y = groundY(x, z)
			local green = rng:NextInteger(85, 125)
			for _ = 1, rng:NextInteger(2, 4) do
				local sz = rng:NextNumber(2.5, 5)
				part({
					Name = "Busch",
					Shape = Enum.PartType.Ball,
					Size = Vector3.new(sz, sz, sz),
					CFrame = CFrame.new(x + rng:NextNumber(-2, 2), y + sz * 0.3, z + rng:NextNumber(-2, 2)),
					Color = Color3.fromRGB(45, green, 40),
					Material = Enum.Material.LeafyGrass,
					CanCollide = false,
					Parent = folder,
				})
			end
			placed += 1
		end
	end

	-- Felsen
	placed, tries = 0, 0
	while placed < 70 and tries < 2000 do
		tries += 1
		local x, z = rng:NextNumber(-1000, 1000), rng:NextNumber(-1000, 1000)
		if isFree(x, z) then
			local sz = Vector3.new(rng:NextNumber(3, 9), rng:NextNumber(2, 5), rng:NextNumber(3, 9))
			part({
				Name = "Fels",
				Size = sz,
				CFrame = CFrame.new(x, groundY(x, z) + sz.Y * 0.2, z) * CFrame.Angles(rng:NextNumber(-0.3, 0.3), rng:NextNumber(0, 6.28), rng:NextNumber(-0.3, 0.3)),
				Color = Color3.fromRGB(rng:NextInteger(105, 135), rng:NextInteger(105, 130), rng:NextInteger(100, 120)),
				Material = Enum.Material.Rock,
				Parent = folder,
			})
			placed += 1
		end
	end

	-- Blumenwiesen
	local FLOWERS = {
		Color3.fromRGB(230, 40, 50), Color3.fromRGB(250, 220, 40), Color3.fromRGB(245, 245, 250),
		Color3.fromRGB(150, 80, 200), Color3.fromRGB(255, 140, 180),
	}
	placed, tries = 0, 0
	while placed < 45 and tries < 1500 do
		tries += 1
		local x, z = rng:NextNumber(-1000, 1000), rng:NextNumber(-1000, 1000)
		if areaFree(x, z, 10) then
			local col = FLOWERS[rng:NextInteger(1, #FLOWERS)]
			for _ = 1, 12 do
				local fx, fz = x + rng:NextNumber(-9, 9), z + rng:NextNumber(-9, 9)
				part({
					Name = "Blume",
					Shape = Enum.PartType.Ball,
					Size = Vector3.new(0.7, 0.7, 0.7),
					CFrame = CFrame.new(fx, groundY(fx, fz) + 0.5, fz),
					Color = col,
					CanCollide = false,
					CastShadow = false,
					Parent = folder,
				})
			end
			placed += 1
		end
	end
end

------------------------------------------------------------------------
-- Straßenmöbel: Bänke, Mülleimer, Bushaltestellen, Schilder
------------------------------------------------------------------------
local function bench(pos, facing)
	local cf = CFrame.lookAt(pos, pos + facing)
	local wood = Color3.fromRGB(130, 90, 55)
	local metal = Color3.fromRGB(45, 48, 52)
	part({ Name = "Bank", Size = Vector3.new(5, 0.3, 1.4), CFrame = cf * CFrame.new(0, 1.5, 0), Color = wood, Material = Enum.Material.WoodPlanks, Parent = folder })
	part({ Name = "Banklehne", Size = Vector3.new(5, 1.2, 0.25), CFrame = cf * CFrame.new(0, 2.4, 0.65), Color = wood, Material = Enum.Material.WoodPlanks, Parent = folder })
	for _, x in ipairs({ -2.1, 2.1 }) do
		part({ Name = "Bankfuss", Size = Vector3.new(0.25, 1.4, 1.3), CFrame = cf * CFrame.new(x, 0.75, 0), Color = metal, Material = Enum.Material.Metal, Parent = folder })
	end
end

local function bin(pos)
	part({ Name = "Muelleimer", Shape = Enum.PartType.Cylinder, Size = Vector3.new(2.4, 1.6, 1.6), CFrame = CFrame.new(pos + Vector3.new(0, 1.2, 0)) * CFrame.Angles(0, 0, math.rad(90)), Color = Color3.fromRGB(40, 110, 60), Material = Enum.Material.Metal, Parent = folder })
end

local function busStop(x)
	local z = World.ROAD_Z + 18.5
	local base = CFrame.new(x, 0.25, z)
	part({ Name = "Wartehaeuschen", Size = Vector3.new(11, 0.3, 4.4), CFrame = base * CFrame.new(0, 8, 0), Color = Color3.fromRGB(60, 62, 68), Material = Enum.Material.Metal, Parent = folder })
	part({ Name = "Rueckwand", Size = Vector3.new(11, 7.6, 0.15), CFrame = base * CFrame.new(0, 4, 2.1), Color = Color3.fromRGB(180, 210, 230), Material = Enum.Material.Glass, Transparency = 0.5, Parent = folder })
	for _, sx in ipairs({ -5.4, 5.4 }) do
		part({ Name = "Seitenglas", Size = Vector3.new(0.15, 7.6, 4.2), CFrame = base * CFrame.new(sx, 4, 0), Color = Color3.fromRGB(180, 210, 230), Material = Enum.Material.Glass, Transparency = 0.5, Parent = folder })
	end
	bench(Vector3.new(x, 0.25, z + 0.8), -Vector3.zAxis)
	part({ Name = "Haltestellenmast", Size = Vector3.new(0.35, 9, 0.35), CFrame = CFrame.new(x - 7.5, 4.75, World.ROAD_Z + 13), Color = Color3.fromRGB(150, 150, 155), Material = Enum.Material.Metal, Parent = folder })
	local sign = part({ Name = "Haltestellenschild", Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.2, 2.6, 2.6), CFrame = CFrame.new(x - 7.5, 9.6, World.ROAD_Z + 13) * CFrame.Angles(0, math.rad(90), 0), Color = Color3.fromRGB(250, 210, 0), Parent = folder })
	local plate = part({ Name = "Haltestelle", Size = Vector3.new(1.6, 1.6, 0.1), CFrame = CFrame.new(x - 7.5, 9.6, World.ROAD_Z + 12.85), Transparency = 1, CanCollide = false, Parent = folder })
	Util.textGui(plate, Enum.NormalId.Front, "H", Color3.fromRGB(0, 120, 60))
	sign.Name = "Haltestellenschild"
end

local function speedSign(pos, facing, text)
	part({ Name = "Schildmast", Size = Vector3.new(0.3, 7, 0.3), CFrame = CFrame.new(pos + Vector3.new(0, 3.5, 0)), Color = Color3.fromRGB(150, 150, 155), Material = Enum.Material.Metal, Parent = folder })
	local cf = CFrame.lookAt(pos + Vector3.new(0, 7.4, 0), pos + Vector3.new(0, 7.4, 0) + facing)
	part({ Name = "Schildring", Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.12, 2.4, 2.4), CFrame = cf * CFrame.Angles(0, math.rad(90), 0), Color = Color3.fromRGB(210, 20, 30), Parent = folder })
	part({ Name = "Schildflaeche", Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.14, 1.9, 1.9), CFrame = cf * CFrame.Angles(0, math.rad(90), 0), Color = Color3.fromRGB(245, 245, 245), Parent = folder })
	local plate = part({ Name = "Schildtext", Size = Vector3.new(1.4, 1.1, 0.05), CFrame = cf * CFrame.new(0, 0, -0.1), Transparency = 1, CanCollide = false, Parent = folder })
	Util.textGui(plate, Enum.NormalId.Front, text, Color3.fromRGB(15, 15, 15))
end

local function directionSign(pos, facing, text)
	part({ Name = "Schildmast", Size = Vector3.new(0.3, 7, 0.3), CFrame = CFrame.new(pos + Vector3.new(0, 3.5, 0)), Color = Color3.fromRGB(150, 150, 155), Material = Enum.Material.Metal, Parent = folder })
	local panel = part({ Name = "Wegweiser", Size = Vector3.new(7, 1.6, 0.15), CFrame = CFrame.lookAt(pos + Vector3.new(0, 7, 0), pos + Vector3.new(0, 7, 0) + facing), Color = Color3.fromRGB(250, 210, 0), Parent = folder })
	Util.textGui(panel, Enum.NormalId.Front, text, Color3.fromRGB(15, 15, 15), Color3.fromRGB(250, 210, 0))
end

local function buildStreetFurniture()
	-- durchgehender Gehweg an der Südseite der Werkstattstraße
	World.Slab(CFrame.new(0, 0, World.ROAD_Z + 16), 1900, 8, 0.25, Color3.fromRGB(178, 176, 172), Enum.Material.Pavement, "Gehweg")
	for x = -870, 870, 90 do
		if math.abs(x) > 40 and math.abs(math.abs(x) - 420) > 20 then
			bench(Vector3.new(x, 0.25, World.ROAD_Z + 18.8), -Vector3.zAxis)
			bin(Vector3.new(x + 4, 0.25, World.ROAD_Z + 19))
		end
	end
	busStop(-420)
	busStop(420)
	speedSign(Vector3.new(-620, 0.25, World.ROAD_Z + 13.5), -Vector3.xAxis, "50")
	speedSign(Vector3.new(620, 0.25, World.ROAD_Z + 13.5), Vector3.xAxis, "50")
	directionSign(Vector3.new(-10.3, 0.2, World.ROAD_Z - 13), Vector3.zAxis, "🏁 Teststrecke")
end

-- Geparkte Autos im Fahrerlager
local function buildParkedCars()
	local rng = Random.new(31)
	local z0 = SOUTH_Z + T.Width / 2 - 1
	local zc = z0 + 70 - 9
	local styles = { "hatch", "sedan", "wagon", "coupe", "super" }
	local colors = { Color3.fromRGB(235, 235, 238), Color3.fromRGB(25, 25, 28), Color3.fromRGB(170, 20, 30), Color3.fromRGB(25, 60, 140), Color3.fromRGB(240, 170, 0), Color3.fromRGB(120, 125, 132) }
	for x = -171, 171, 10 do
		if math.abs(x) > 30 and rng:NextNumber() < 0.45 then
			local car = Cars.MakeShowCar({ Name = "Geparkt", Style = styles[rng:NextInteger(1, #styles)], Hp = rng:NextInteger(150, 600), Color = colors[rng:NextInteger(1, #colors)] })
			car.PrimaryPart.CFrame = CFrame.new(x, 0.07 + Cars.BODY_HEIGHT, zc) * CFrame.Angles(0, math.pi, 0)
			car.Kollision.CanCollide = true
			car.Parent = folder
		end
	end
end

------------------------------------------------------------------------
-- Aufbau
------------------------------------------------------------------------
function World.Build()
	folder = Instance.new("Folder")
	folder.Name = "Welt"
	folder.Parent = workspace

	buildLighting()
	buildTerrain()
	buildHills()
	buildRoads()
	buildTrack()
	buildPaddock()
	buildStreetFurniture()
	buildLamps()
	buildTown()
	buildTrees()
	buildNatureDetails()
	buildParkedCars()

	local spawnLoc = Instance.new("SpawnLocation")
	spawnLoc.Name = "Spawn"
	spawnLoc.Anchored = true
	spawnLoc.Size = Vector3.new(12, 1, 12)
	World.Slab(CFrame.new(0, 0, World.ROAD_Z + 30), 24, 22, 0.4, Color3.fromRGB(175, 175, 178), Enum.Material.Pavement, "SpawnPlatz")
	spawnLoc.CFrame = CFrame.new(0, 0.5, World.ROAD_Z + 30)
	spawnLoc.Neutral = true
	spawnLoc.Duration = 0
	spawnLoc.Material = Enum.Material.SmoothPlastic
	spawnLoc.Color = Color3.fromRGB(255, 140, 0)
	spawnLoc.Parent = folder

	local vehicles = Instance.new("Folder")
	vehicles.Name = "Fahrzeuge"
	vehicles.Parent = workspace
	World.Vehicles = vehicles
	World.Folder = folder
end

-- Startplatz auf der Start-Ziel-Geraden (Fahrtrichtung +X)
function World.TrackStart(index)
	local x = -60 - (index - 1) * 18
	local z = SOUTH_Z + ((index % 2 == 0) and 6 or -6)
	local pos = Vector3.new(x, 0.09 + 0.9, z)
	return CFrame.lookAt(pos, pos + Vector3.xAxis)
end

return World
