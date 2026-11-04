-- Chiptuning-Firma: Server
-- Script "GameServer" in ServerScriptService

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local DataStoreService = game:GetService("DataStoreService")
local Lighting = game:GetService("Lighting")
local RunService = game:GetService("RunService")
local MarketplaceService = game:GetService("MarketplaceService")

local Config = require(ReplicatedStorage:WaitForChild("Config"))

------------------------------------------------------------------------
-- Remotes
------------------------------------------------------------------------
local remotes = Instance.new("Folder")
remotes.Name = "Remotes"

local function newRemote(name)
	local r = Instance.new("RemoteEvent")
	r.Name = name
	r.Parent = remotes
	return r
end

local OpenTuning = newRemote("OpenTuning") -- Server -> Client: Tuning-Fenster öffnen
local FinishTuning = newRemote("FinishTuning") -- Client -> Server: Nadel-Positionen
local CancelTuning = newRemote("CancelTuning") -- Client -> Server
local TuneResult = newRemote("TuneResult") -- Server -> Client: Ergebnis
local OpenShop = newRemote("OpenShop") -- Server -> Client
local BuyUpgrade = newRemote("BuyUpgrade") -- Client -> Server
local Notify = newRemote("Notify") -- Server -> Client: Meldung
local RequestTestDrive = newRemote("RequestTestDrive") -- Client -> Server
local RequestCompanyCar = newRemote("RequestCompanyCar") -- Client -> Server
local EndDrive = newRemote("EndDrive") -- Client -> Server
local AdminAction = newRemote("AdminAction") -- Client -> Server (nur Admins)
remotes.Parent = ReplicatedStorage

local function notify(player, text, kind)
	Notify:FireClient(player, text, kind or "info")
end

-- Sound am Server (alle hören ihn). key = Eintrag in Config.Sounds oder direkte ID
local function playSound(parent, key, volume, looped)
	local id = Config.SoundId(key) or (key:find("://") and key) or nil
	if not id or not parent then
		return nil
	end
	local snd = Instance.new("Sound")
	snd.SoundId = id
	snd.Volume = volume or 0.7
	snd.Looped = looped or false
	snd.RollOffMode = Enum.RollOffMode.InverseTapered
	snd.RollOffMinDistance = 10
	snd.RollOffMaxDistance = 160
	snd.Parent = parent
	if not looped then
		snd:Play()
		task.delay(4, function()
			snd:Destroy()
		end)
	end
	return snd
end

------------------------------------------------------------------------
-- Module
------------------------------------------------------------------------
local Util = require(ReplicatedStorage:WaitForChild("Util"))
local World = require(script.Parent:WaitForChild("World"))
local Cars = require(ReplicatedStorage:WaitForChild("Cars"))
local Npc = require(ReplicatedStorage:WaitForChild("Npc"))

local part, textGui, billboard = Util.part, Util.textGui, Util.billboard
local lookCF, moveModel = Util.lookCF, Util.moveModel

World.Build()
Npc.BuildTemplates(12)

local ROAD_Z = World.ROAD_Z
local PLOT_SPACING = World.PLOT_SPACING
local BAY_X = { -27, -9, 9, 27 }
local BAY_Z = -12
local DYNO_POS = Vector3.new(26, 0, 18)
local LIFT_TOP = 1.0 -- Oberkante der Fahrschienen (unten)
local LIFT_UP = 5.5 -- so weit fährt die Bühne hoch

------------------------------------------------------------------------
-- Spielerdaten
------------------------------------------------------------------------
local store = nil
do
	local ok, result = pcall(function()
		return DataStoreService:GetDataStore(Config.DataStoreName)
	end)
	if ok then
		store = result
	else
		warn("[Chiptuning] DataStore nicht verfügbar: " .. tostring(result))
	end
end

local States = {} -- [player] = Zustand
local usedPlots = {} -- [index] = player
local jobCounter = 0

local function defaultData()
	return { Money = Config.StartMoney, Rep = 0, Tunes = 0, Upgrades = {}, Receipts = {} }
end

local function loadData(player)
	if not store then
		return defaultData(), false
	end
	local ok, res = pcall(function()
		return store:GetAsync("p_" .. player.UserId)
	end)
	if not ok then
		warn("[Chiptuning] Laden fehlgeschlagen: " .. tostring(res))
		return defaultData(), false
	end
	local data = defaultData()
	if type(res) == "table" then
		data.Money = tonumber(res.Money) or data.Money
		data.Rep = tonumber(res.Rep) or 0
		data.Tunes = tonumber(res.Tunes) or 0
		if type(res.Upgrades) == "table" then
			for id, owned in pairs(res.Upgrades) do
				if owned == true and Config.GetUpgrade(id) then
					data.Upgrades[id] = true
				end
			end
		end
		if type(res.Receipts) == "table" then
			for _, r in ipairs(res.Receipts) do
				if type(r) == "string" then
					table.insert(data.Receipts, r)
				end
			end
		end
	end
	return data, true
end

-- Gibt true zurück, wenn gespeichert wurde
local function saveData(player, st)
	if not (store and st.CanSave) then
		return false
	end
	local ok, err = pcall(function()
		store:SetAsync("p_" .. player.UserId, {
			Money = st.Data.Money,
			Rep = st.Data.Rep,
			Tunes = st.Data.Tunes,
			Upgrades = st.Data.Upgrades,
			Receipts = st.Data.Receipts,
		})
	end)
	if not ok then
		warn("[Chiptuning] Speichern fehlgeschlagen: " .. tostring(err))
	end
	return ok
end

local function hasUpgrade(st, id)
	return st.Data.Upgrades[id] == true
end

local function hasPass(st, key)
	return st.Passes[key] == true
end

local function maxStage(st)
	if hasUpgrade(st, "Stage3") then
		return 3
	elseif hasUpgrade(st, "Stage2") then
		return 2
	end
	return 1
end

local function isBayUnlocked(st, index)
	return index == 1 or hasUpgrade(st, "Bay" .. index)
end

local function setMoney(st, value)
	st.Data.Money = value
	st.MoneyValue.Value = value
end

local function setRep(st, value)
	st.Data.Rep = value
	st.RepValue.Value = value
end

-- Karosseriemitte über dem Boden (Ausstellungsautos)
local CAR_HEIGHT = Cars.BODY_HEIGHT

------------------------------------------------------------------------
-- Werkstatt (Grundstück)
------------------------------------------------------------------------
local function buildLock(plot, bay)
	local lock = part({
		Name = "Gesperrt",
		Size = Vector3.new(14, 6, 22),
		CFrame = plot.Origin * CFrame.new(bay.X, 4, BAY_Z),
		Color = Color3.fromRGB(200, 40, 40),
		Material = Enum.Material.ForceField,
		Transparency = 0.3,
		CanCollide = false,
		Parent = plot.Model,
	})
	billboard(lock, "🔒 Hebebühne " .. bay.Index .. "\nim Shop freischalten", 1)
	bay.Lock = lock
end

local function buildDyno(plot, owned)
	if plot.Dyno then
		plot.Dyno:Destroy()
	end
	local dyno = Instance.new("Model")
	dyno.Name = "Pruefstand"
	local base = plot.Origin * CFrame.new(DYNO_POS)
	local pad = part({
		Name = "Platte",
		Size = Vector3.new(10, 0.4, 16),
		CFrame = base * CFrame.new(0, 0.6, 0),
		Color = owned and Color3.fromRGB(40, 40, 45) or Color3.fromRGB(120, 120, 125),
		Material = Enum.Material.DiamondPlate,
		Transparency = owned and 0 or 0.6,
		Parent = dyno,
	})
	if owned then
		for _, z in ipairs({ -3.8, 3.8 }) do
			part({
				Name = "Rolle",
				Shape = Enum.PartType.Cylinder,
				Size = Vector3.new(8, 1, 1),
				CFrame = base * CFrame.new(0, 0.85, z),
				Color = Color3.fromRGB(180, 180, 190),
				Material = Enum.Material.Metal,
				CanCollide = false,
				Parent = dyno,
			})
		end
		local screen = part({
			Name = "Monitor",
			Size = Vector3.new(6, 4, 0.4),
			CFrame = base * CFrame.new(7, 5, -4) * CFrame.Angles(0, math.rad(-35), 0),
			Color = Color3.fromRGB(10, 10, 12),
			Parent = dyno,
		})
		part({
			Name = "Staender",
			Size = Vector3.new(0.4, 3, 0.4),
			CFrame = base * CFrame.new(7, 1.9, -4),
			Color = Color3.fromRGB(60, 60, 60),
			Parent = dyno,
		})
		plot.DynoScreen = textGui(screen, Enum.NormalId.Back, "PRÜFSTAND\nbereit", Color3.fromRGB(80, 255, 120), Color3.fromRGB(10, 14, 12))
	else
		billboard(pad, "Leistungsprüfstand\n(im Shop kaufen)", 3)
		plot.DynoScreen = nil
	end
	dyno.Parent = plot.Model
	plot.Dyno = dyno
end

local function buildPlot(player, st, index)
	local origin = CFrame.new((index - (Config.MaxPlots + 1) / 2) * PLOT_SPACING, 0, 0)
	local model = Instance.new("Model")
	model.Name = "Werkstatt_" .. player.Name
	local plot = { Index = index, Origin = origin, Model = model, Bays = {} }

	local function at(x, y, z)
		return origin * CFrame.new(x, y, z)
	end
	local function p(props)
		props.Parent = props.Parent or model
		return part(props)
	end

	local wall = Color3.fromRGB(232, 232, 236)
	local dark = Color3.fromRGB(32, 33, 38)
	local steel = Color3.fromRGB(70, 72, 78)
	local accent = Color3.fromRGB(255, 140, 0)

	-- Fundament: Gelände entfernen, Betonplatte rund um die Halle
	World.Slab(at(0, 0, 3), 84, 76, 0.1, Color3.fromRGB(150, 150, 154), Enum.Material.Concrete, "Fundament", model)
	-- Hallenboden: dunkle Fliesen mit leichtem Glanz
	p({ Name = "Hallenboden", Size = Vector3.new(76, 0.2, 64), CFrame = at(0, 0.1, 0), Color = Color3.fromRGB(78, 80, 88), Material = Enum.Material.CeramicTiles, Reflectance = 0.05 })
	p({ Name = "Einfahrt", Size = Vector3.new(76, 0.1, 7), CFrame = at(0, 0.15, 36.5), Color = Color3.fromRGB(70, 71, 76), Material = Enum.Material.Asphalt })
	p({ Name = "Gehweglinie", Size = Vector3.new(76, 0.04, 0.6), CFrame = at(0, 0.22, 4), Color = Color3.fromRGB(255, 200, 0), CanCollide = false })
	-- Bodenablauf-Rinne
	p({ Name = "Rinne", Size = Vector3.new(60, 0.04, 0.8), CFrame = at(0, 0.22, 2), Color = Color3.fromRGB(40, 40, 44), Material = Enum.Material.DiamondPlate, CanCollide = false })

	-- Wände (außen Ziegel, innen hell) mit dunklem Sockel und LED-Band
	p({ Name = "Rueckwand", Size = Vector3.new(78, 20, 1.2), CFrame = at(0, 10, -32.6), Color = wall, Material = Enum.Material.SmoothPlastic })
	p({ Name = "WandLinks", Size = Vector3.new(1.2, 20, 66), CFrame = at(-38.6, 10, 0), Color = wall, Material = Enum.Material.SmoothPlastic })
	p({ Name = "WandRechts", Size = Vector3.new(1.2, 20, 66), CFrame = at(38.6, 10, 0), Color = wall, Material = Enum.Material.SmoothPlastic })
	p({ Name = "AussenLinks", Size = Vector3.new(0.4, 20, 66.4), CFrame = at(-39.4, 10, 0), Color = Color3.fromRGB(120, 60, 45), Material = Enum.Material.Brick })
	p({ Name = "AussenRechts", Size = Vector3.new(0.4, 20, 66.4), CFrame = at(39.4, 10, 0), Color = Color3.fromRGB(120, 60, 45), Material = Enum.Material.Brick })
	p({ Name = "AussenHinten", Size = Vector3.new(79.2, 20, 0.4), CFrame = at(0, 10, -33.4), Color = Color3.fromRGB(120, 60, 45), Material = Enum.Material.Brick })
	p({ Name = "SockelHinten", Size = Vector3.new(76, 3, 0.3), CFrame = at(0, 1.7, -31.9), Color = dark, CanCollide = false })
	p({ Name = "SockelLinks", Size = Vector3.new(0.3, 3, 64), CFrame = at(-37.9, 1.7, 0), Color = dark, CanCollide = false })
	p({ Name = "SockelRechts", Size = Vector3.new(0.3, 3, 64), CFrame = at(37.9, 1.7, 0), Color = dark, CanCollide = false })
	plot.Strip = p({ Name = "Streifen", Size = Vector3.new(76, 0.5, 0.2), CFrame = at(0, 7, -31.85), Color = accent, Material = Enum.Material.Neon, CanCollide = false })
	p({ Name = "StreifenL", Size = Vector3.new(0.2, 0.5, 64), CFrame = at(-37.85, 7, 0), Color = accent, Material = Enum.Material.Neon, CanCollide = false })
	p({ Name = "StreifenR", Size = Vector3.new(0.2, 0.5, 64), CFrame = at(37.85, 7, 0), Color = accent, Material = Enum.Material.Neon, CanCollide = false })

	local backSign = p({ Name = "Wandschild", Size = Vector3.new(40, 4, 0.2), CFrame = at(0, 13, -31.85), Color = Color3.fromRGB(20, 20, 25), CanCollide = false })
	textGui(backSign, Enum.NormalId.Back, "ECU · STAGE 1 · 2 · 3 · DYNO", accent, Color3.fromRGB(20, 20, 25))

	-- Front: Pfeiler und beleuchtetes Firmenschild
	for _, x in ipairs({ -38.6, 38.6 }) do
		p({ Name = "Pfeiler", Size = Vector3.new(2.4, 24, 2.4), CFrame = at(x, 12, 33), Color = dark, Material = Enum.Material.Metal })
	end
	local sign = p({ Name = "Firmenschild", Size = Vector3.new(79, 4.5, 1.2), CFrame = at(0, 21.5, 33), Color = Color3.fromRGB(18, 18, 22) })
	plot.SignLabel = textGui(sign, Enum.NormalId.Back, player.DisplayName .. "s Chiptuning", accent, Color3.fromRGB(18, 18, 22))
	p({ Name = "SchildLicht", Size = Vector3.new(79, 0.3, 0.3), CFrame = at(0, 19.1, 33.7), Color = accent, Material = Enum.Material.Neon, CanCollide = false })

	-- Stahlträger und Hallenlicht (kein Dach, damit die Kamera frei bleibt)
	for _, z in ipairs({ -24, -8, 8, 24 }) do
		p({ Name = "Traeger", Size = Vector3.new(78, 1.2, 0.8), CFrame = at(0, 19.4, z), Color = steel, Material = Enum.Material.Metal })
	end
	for _, x in ipairs({ -20, 0, 20 }) do
		p({ Name = "Laengstraeger", Size = Vector3.new(0.8, 0.8, 66), CFrame = at(x, 20.2, 0), Color = steel, Material = Enum.Material.Metal })
	end
	for _, bx in ipairs(BAY_X) do
		local panel = p({ Name = "Hallenlicht", Size = Vector3.new(10, 0.3, 1.6), CFrame = at(bx, 18.6, BAY_Z), Color = Color3.fromRGB(240, 245, 255), Material = Enum.Material.Neon, CanCollide = false })
		Util.light(panel, "SurfaceLight", { Face = Enum.NormalId.Bottom, Range = 22, Brightness = 1.6, Angle = 110, Color = Color3.fromRGB(235, 242, 255) })
		p({ Name = "Seil", Size = Vector3.new(0.1, 0.8, 0.1), CFrame = at(bx, 19.1, BAY_Z), Color = steel, CanCollide = false })
	end

	-- 4-Säulen-Hebebühnen
	local liftRed = Color3.fromRGB(200, 30, 35)
	local metal = Color3.fromRGB(105, 108, 116)
	for i, bx in ipairs(BAY_X) do
		local bay = { Index = i, X = bx, CF = at(bx, LIFT_TOP + CAR_HEIGHT, BAY_Z), Car = nil, Lock = nil, LiftH = 0, LiftParts = {} }
		plot.Bays[i] = bay
		local function moving(props)
			local mp = p(props)
			table.insert(bay.LiftParts, { Part = mp, Base = mp.CFrame })
			return mp
		end
		-- Fahrschienen (bewegen sich)
		for _, side in ipairs({ -1, 1 }) do
			moving({ Name = "Fahrschiene", Size = Vector3.new(2.8, 0.6, 20), CFrame = at(bx + side * 3.05, LIFT_TOP - 0.3, BAY_Z), Color = metal, Material = Enum.Material.DiamondPlate })
			moving({ Name = "Schienenkante", Size = Vector3.new(0.25, 0.35, 20), CFrame = at(bx + side * 4.55, LIFT_TOP + 0.1, BAY_Z), Color = Color3.fromRGB(255, 200, 0), Material = Enum.Material.SmoothPlastic })
			-- Auffahrrampe (fest)
			local ramp = Util.wedge({
				Name = "Rampe",
				Size = Vector3.new(2.8, LIFT_TOP - 0.2, 2.6),
				CFrame = at(bx + side * 3.05, 0.2 + (LIFT_TOP - 0.2) / 2, BAY_Z + 11.3) * CFrame.Angles(0, math.pi, 0),
				Color = metal,
				Material = Enum.Material.DiamondPlate,
				Parent = model,
			})
			ramp.Name = "Rampe"
		end
		-- Querträger vorne/hinten (bewegen sich)
		for _, dz in ipairs({ -10.4, 10.4 }) do
			moving({ Name = "Quertraeger", Size = Vector3.new(10.6, 0.7, 1.2), CFrame = at(bx, LIFT_TOP - 0.45, BAY_Z + dz), Color = liftRed, Material = Enum.Material.Metal })
		end
		-- Säulen und obere Träger (fest)
		for _, dx in ipairs({ -5.6, 5.6 }) do
			for _, dz in ipairs({ -10.4, 10.4 }) do
				p({ Name = "Saeule", Size = Vector3.new(1.1, 10, 1.1), CFrame = at(bx + dx, 5.2, BAY_Z + dz), Color = liftRed, Material = Enum.Material.Metal })
				p({ Name = "SaeulenFuss", Size = Vector3.new(1.8, 0.3, 1.8), CFrame = at(bx + dx, 0.35, BAY_Z + dz), Color = Color3.fromRGB(35, 35, 38), Material = Enum.Material.Metal })
			end
		end
		for _, dz in ipairs({ -10.4, 10.4 }) do
			p({ Name = "Obertraeger", Size = Vector3.new(12.3, 0.8, 1.1), CFrame = at(bx, 10.6, BAY_Z + dz), Color = liftRed, Material = Enum.Material.Metal })
		end
		-- Warnleuchte
		local beacon = p({ Name = "Warnleuchte", Shape = Enum.PartType.Ball, Size = Vector3.new(0.9, 0.9, 0.9), CFrame = at(bx + 5.6, 11.4, BAY_Z + 10.4), Color = Color3.fromRGB(255, 150, 0), Material = Enum.Material.SmoothPlastic })
		bay.Beacon = beacon
		bay.BeaconLight = Util.light(beacon, "PointLight", { Range = 16, Brightness = 0, Color = Color3.fromRGB(255, 150, 0), Enabled = false })
		bay.LiftSound = playSound(bay.LiftParts[1] and bay.LiftParts[1].Part, "Hydraulik", 0.6, true)
		-- Warnstreifen am Boden rund um die Bühne
		for k = 0, 9 do
			for _, side in ipairs({ -1, 1 }) do
				p({
					Name = "Warnstreifen",
					Size = Vector3.new(0.6, 0.04, 2.2),
					CFrame = at(bx + side * 6.6, 0.22, BAY_Z - 10 + k * 2.2),
					Color = (k % 2 == 0) and Color3.fromRGB(255, 200, 0) or Color3.fromRGB(25, 25, 25),
					CanCollide = false,
				})
			end
		end
		-- Diagnose-Wagen mit Laptop zwischen den Bühnen
		local cartPos = at(bx + 9, 0, BAY_Z + 7)
		p({ Name = "Diagnosewagen", Size = Vector3.new(1.8, 3, 1.4), CFrame = cartPos * CFrame.new(0, 1.7, 0), Color = Color3.fromRGB(30, 32, 38), Material = Enum.Material.Metal })
		local screen = p({ Name = "Diagnosebildschirm", Size = Vector3.new(1.8, 1.2, 0.1), CFrame = cartPos * CFrame.new(0, 3.9, 0) * CFrame.Angles(math.rad(-15), 0, 0), Color = Color3.fromRGB(15, 25, 35), Material = Enum.Material.Neon, Transparency = 0.2 })
		bay.CartScreen = textGui(screen, Enum.NormalId.Back, "OBD", Color3.fromRGB(80, 200, 255), Color3.fromRGB(10, 20, 30))
		local att = Instance.new("Attachment")
		att.Name = "Kabel"
		att.Position = Vector3.new(0, -0.6, 0)
		att.Parent = screen
		bay.CartAttachment = att

		if not isBayUnlocked(st, i) then
			buildLock(plot, bay)
		end
	end

	-- Werkzeugwagen an der linken Wand
	for k, z in ipairs({ -26, 8, 16 }) do
		p({ Name = "Werkzeugwagen", Size = Vector3.new(3, 4.4, 6), CFrame = at(-36, 2.4, z), Color = Color3.fromRGB(190, 25, 30), Material = Enum.Material.SmoothPlastic, Reflectance = 0.08 })
		for d = 0, 3 do
			p({ Name = "Schublade", Size = Vector3.new(0.1, 0.12, 5.4), CFrame = at(-34.45, 1.2 + d * 1.0, z), Color = Color3.fromRGB(20, 20, 22), CanCollide = false })
		end
		if k == 1 then
			p({ Name = "Werkbank", Size = Vector3.new(3, 0.3, 6), CFrame = at(-36, 4.75, z), Color = Color3.fromRGB(150, 150, 155), Material = Enum.Material.Metal })
		end
	end

	-- Reifenstapel an der rechten Wand
	for _, z in ipairs({ -26, -21, 2 }) do
		for h = 0, 3 do
			p({ Name = "Reifen", Shape = Enum.PartType.Cylinder, Size = Vector3.new(0.9, 3, 3), CFrame = at(35.6, 0.65 + h * 0.92, z) * CFrame.Angles(0, 0, math.rad(90)), Color = Color3.fromRGB(25, 25, 27) })
		end
	end

	-- Plakate an den Seitenwänden
	local posters = {
		{ -37.8, -14, Enum.NormalId.Right, "STAGE 1\n+20 % Leistung" },
		{ -37.8, 0, Enum.NormalId.Right, "STAGE 2\n+35 % Leistung" },
		{ 37.8, -12, Enum.NormalId.Left, "STAGE 3\n+55 % Leistung" },
		{ 37.8, 8, Enum.NormalId.Left, "DYNO\nGEPRÜFT ✔" },
	}
	for _, ps in ipairs(posters) do
		local poster = p({ Name = "Plakat", Size = Vector3.new(0.1, 5, 7), CFrame = at(ps[1], 11, ps[2]), Color = Color3.fromRGB(20, 20, 25), CanCollide = false })
		textGui(poster, ps[3], ps[4], accent, Color3.fromRGB(20, 20, 25))
	end

	-- Büro-Ecke: Schreibtisch mit Laptop = Upgrade-Shop
	p({ Name = "Tisch", Size = Vector3.new(7, 0.4, 3.5), CFrame = at(-31, 3.2, 24), Color = Color3.fromRGB(110, 75, 50), Material = Enum.Material.Wood })
	for _, dx in ipairs({ -3.2, 3.2 }) do
		p({ Name = "Tischbein", Size = Vector3.new(0.3, 3, 3.2), CFrame = at(-31 + dx, 1.6, 24), Color = dark, Material = Enum.Material.Metal })
	end
	p({ Name = "Stuhl", Size = Vector3.new(2, 0.5, 2), CFrame = at(-31, 2, 27), Color = Color3.fromRGB(25, 25, 28), Material = Enum.Material.Fabric })
	p({ Name = "Lehne", Size = Vector3.new(2, 2.4, 0.4), CFrame = at(-31, 3.4, 28), Color = Color3.fromRGB(25, 25, 28), Material = Enum.Material.Fabric })
	local laptop = p({ Name = "Laptop", Size = Vector3.new(2.4, 0.15, 1.6), CFrame = at(-31, 3.48, 24.3), Color = Color3.fromRGB(30, 30, 35), Material = Enum.Material.Metal })
	local lid = p({ Name = "Bildschirm", Size = Vector3.new(2.4, 1.6, 0.1), CFrame = at(-31, 4.3, 23.5) * CFrame.Angles(math.rad(-12), 0, 0), Color = Color3.fromRGB(30, 30, 35) })
	textGui(lid, Enum.NormalId.Back, "ECU", Color3.fromRGB(80, 200, 255), Color3.fromRGB(10, 20, 30))
	Util.light(lid, "SurfaceLight", { Face = Enum.NormalId.Back, Range = 6, Brightness = 1, Color = Color3.fromRGB(80, 200, 255) })
	billboard(laptop, "🛠️ Upgrade-Shop", 3)

	local shopPrompt = Instance.new("ProximityPrompt")
	shopPrompt.ActionText = "Upgrade-Shop öffnen"
	shopPrompt.ObjectText = "Laptop"
	shopPrompt.KeyboardKeyCode = Enum.KeyCode.E
	shopPrompt.MaxActivationDistance = 12
	shopPrompt.RequiresLineOfSight = false
	shopPrompt.Parent = laptop
	shopPrompt.Triggered:Connect(function(who)
		if who == player then
			OpenShop:FireClient(player)
		else
			notify(who, "Das ist nicht deine Werkstatt!", "bad")
		end
	end)

	-- Parkplatz für den Firmenwagen neben der Halle (in der Lücke zum Nachbarn)
	local spotX = index <= Config.MaxPlots / 2 and -50 or 50
	World.Slab(at(spotX, 0, 21.5), 15, 37, 0.05, Color3.fromRGB(70, 72, 78), Enum.Material.Asphalt, "Parkplatz", model)
	for _, dx in ipairs({ -5, 5 }) do
		p({ Name = "Parklinie", Size = Vector3.new(0.4, 0.05, 16), CFrame = at(spotX + dx, 0.08, 18), Color = Color3.new(1, 1, 1), CanCollide = false })
	end
	local pSign = p({ Name = "Parkschild", Size = Vector3.new(6, 2, 0.3), CFrame = at(spotX, 5, 5), Color = Color3.fromRGB(30, 90, 200) })
	textGui(pSign, Enum.NormalId.Back, "P  Firmenwagen", Color3.new(1, 1, 1), Color3.fromRGB(30, 90, 200))
	p({ Name = "Schildpfosten", Size = Vector3.new(0.3, 4, 0.3), CFrame = at(spotX, 2, 5), Color = Color3.fromRGB(120, 120, 125) })
	plot.CarSpot = at(spotX, 0.05 + Cars.CHASSIS_HEIGHT + 0.3, 20) * CFrame.Angles(0, math.pi, 0)

	model.Parent = World.Folder
	buildDyno(plot, hasUpgrade(st, "Dyno"))
	return plot
end

------------------------------------------------------------------------
-- Hebebühnen-Animation und Effekte
------------------------------------------------------------------------
local ORANGE = Color3.fromRGB(255, 140, 0)

local function setLift(bay, h)
	bay.LiftH = h
	for _, lp in ipairs(bay.LiftParts) do
		if lp.Part.Parent then
			lp.Part.CFrame = lp.Base + Vector3.new(0, h, 0)
		end
	end
	local c = bay.Car
	if c and c.OnLift and c.Model.Parent and c.Model.PrimaryPart then
		c.Model.PrimaryPart.CFrame = bay.CF + Vector3.new(0, h, 0)
	end
end

-- Fährt die Bühne weich auf die Zielhöhe (blockiert, bis fertig)
local function animateLift(bay, target, duration)
	bay.LiftToken = (bay.LiftToken or 0) + 1
	local token = bay.LiftToken
	local from = bay.LiftH or 0
	if math.abs(from - target) < 0.01 then
		return
	end
	if bay.BeaconLight then
		bay.BeaconLight.Enabled = true
		bay.Beacon.Material = Enum.Material.Neon
	end
	if bay.LiftSound then
		bay.LiftSound:Play()
	end
	local t0 = os.clock()
	while bay.LiftToken == token do
		local a = math.clamp((os.clock() - t0) / duration, 0, 1)
		local e = a * a * (3 - 2 * a)
		setLift(bay, from + (target - from) * e)
		if bay.BeaconLight then
			bay.BeaconLight.Brightness = (math.floor(os.clock() * 5) % 2 == 0) and 4 or 0.3
		end
		if a >= 1 then
			break
		end
		RunService.Heartbeat:Wait()
	end
	if bay.LiftToken == token and bay.BeaconLight then
		bay.BeaconLight.Enabled = false
		bay.Beacon.Material = Enum.Material.SmoothPlastic
	end
	if bay.LiftToken == token and bay.LiftSound then
		bay.LiftSound:Stop()
	end
end

-- Funkenregen (z. B. wenn die Software fertig ist)
local function sparkle(target)
	local pe = Instance.new("ParticleEmitter")
	pe.Rate = 0
	pe.Lifetime = NumberRange.new(0.6, 1.3)
	pe.Speed = NumberRange.new(8, 18)
	pe.SpreadAngle = Vector2.new(180, 180)
	pe.LightEmission = 1
	pe.Size = NumberSequence.new({ NumberSequenceKeypoint.new(0, 0.6), NumberSequenceKeypoint.new(1, 0) })
	pe.Color = ColorSequence.new(Color3.fromRGB(255, 220, 80), Color3.fromRGB(80, 255, 140))
	pe.Acceleration = Vector3.new(0, -35, 0)
	pe.Parent = target
	pe:Emit(70)
	task.delay(2.5, function()
		pe:Destroy()
	end)
end

-- Flammen und Licht aus dem Auspuff
local function backfire(carModel, duration)
	local first = true
	for _, d in ipairs(carModel:GetDescendants()) do
		if d.Name == "Auspuff" and d:IsA("BasePart") then
			local f = Instance.new("Fire")
			f.Size = 3
			f.Heat = 4
			f.Color = Color3.fromRGB(255, 110, 20)
			f.SecondaryColor = Color3.fromRGB(255, 230, 90)
			f.Parent = d
			local l = Util.light(d, "PointLight", { Range = 12, Brightness = 3, Color = ORANGE })
			if first then
				first = false
				playSound(d, "Fehlzuendung", 0.9)
			end
			task.delay(duration, function()
				f.Enabled = false
				l:Destroy()
				task.delay(1.5, function()
					f:Destroy()
				end)
			end)
		end
	end
end

-- Abgasrauch
local function exhaustSmoke(carModel, duration)
	for _, d in ipairs(carModel:GetDescendants()) do
		if d.Name == "Auspuff" and d:IsA("BasePart") then
			local sm = Instance.new("Smoke")
			sm.Color = Color3.fromRGB(150, 150, 155)
			sm.Opacity = 0.12
			sm.RiseVelocity = 3
			sm.Size = 2
			sm.Parent = d
			task.delay(duration, function()
				sm.Enabled = false
				task.delay(3, function()
					sm:Destroy()
				end)
			end)
		end
	end
end

-- Leuchtendes Diagnosekabel vom Wagen zum Auto
local function connectCable(bay, carInfo)
	local root = carInfo.Model.PrimaryPart
	if not (root and bay.CartAttachment) then
		return
	end
	local a1 = Instance.new("Attachment")
	a1.Name = "OBD"
	a1.Position = Vector3.new(3.1, 0.2, -1.6)
	a1.Parent = root
	local beam = Instance.new("Beam")
	beam.Attachment0 = bay.CartAttachment
	beam.Attachment1 = a1
	beam.Width0 = 0.18
	beam.Width1 = 0.18
	beam.CurveSize0 = -3
	beam.CurveSize1 = 2
	beam.Segments = 16
	beam.FaceCamera = true
	beam.LightEmission = 1
	beam.Color = ColorSequence.new(Color3.fromRGB(80, 200, 255))
	beam.Transparency = NumberSequence.new(0.05)
	beam.Parent = root
	local glow = Util.light(root, "PointLight", { Range = 10, Brightness = 1.5, Color = Color3.fromRGB(80, 200, 255) })
	carInfo.Cable = { beam, a1, glow }
end

local function removeCable(carInfo)
	for _, inst in ipairs(carInfo.Cable or {}) do
		inst:Destroy()
	end
	carInfo.Cable = nil
end

local function setCartText(bay, text)
	if bay.CartScreen and bay.CartScreen.Parent then
		bay.CartScreen.Text = text
	end
end

------------------------------------------------------------------------
-- Kunden und Aufträge
------------------------------------------------------------------------
local startJob -- wird weiter unten definiert

local function spawnCustomer(player, st, bay)
	local candidates = {}
	for _, c in ipairs(Config.Cars) do
		if st.Data.Rep >= c.MinRep then
			table.insert(candidates, c)
		end
	end
	local def = candidates[math.random(#candidates)]
	local stage = math.random(1, maxStage(st))
	local car = Cars.MakeShowCar(def)
	local customer = Npc.Random()
	if customer then
		Npc.SeatInCar(customer, car)
	end
	local carInfo = { Def = def, Stage = stage, Model = car, Ready = false, Busy = false, Customer = customer }
	bay.Car = carInfo

	local plot = st.Plot
	-- rechte Fahrspur der Werkstattstraße (Rechtsverkehr)
	local roadPos = (plot.Origin * CFrame.new(bay.X, 0, ROAD_Z + 5)).Position + Vector3.new(0, CAR_HEIGHT + World.ROAD_TOP, 0)
	local startCF = lookCF(roadPos - Vector3.new(140, 0, 0), Vector3.xAxis)
	local turnCF = lookCF(roadPos, Vector3.xAxis)
	local facingIn = lookCF(roadPos, -Vector3.zAxis)
	car:PivotTo(startCF)
	car.Parent = plot.Model

	task.spawn(function()
		moveModel(car, startCF, turnCF, 3)
		moveModel(car, turnCF, facingIn, 0.6)
		moveModel(car, facingIn, bay.CF, 3)
		if not car.Parent then
			return
		end
		local stageDef = Config.Stages[stage]
		carInfo.Label = billboard(car.PrimaryPart, ("🚗 %s\nWunsch: %s · %d PS"):format(def.Name, stageDef.Name, def.Hp), 5)

		local prompt = Instance.new("ProximityPrompt")
		prompt.ActionText = "Chiptuning starten"
		prompt.ObjectText = def.Name .. " (" .. stageDef.Name .. ")"
		prompt.KeyboardKeyCode = Enum.KeyCode.E
		prompt.HoldDuration = 0.3
		prompt.MaxActivationDistance = 14
		prompt.RequiresLineOfSight = false
		prompt.Parent = car.PrimaryPart
		carInfo.Prompt = prompt
		prompt.Triggered:Connect(function(who)
			if who ~= player then
				notify(who, "Das ist nicht deine Werkstatt!", "bad")
				return
			end
			startJob(player, st, bay, carInfo)
		end)
		car.Kollision.CanCollide = true
		carInfo.OnLift = true
		-- Kunde steigt aus und wartet neben der Bühne
		if customer then
			local spot = plot.Origin * CFrame.new(bay.X - 7.2, 0.2, BAY_Z + 13)
			Npc.StandAt(customer, CFrame.lookAt(spot.Position, spot.Position + Vector3.new(1, 0, -0.6)), plot.Model)
		end
		carInfo.Ready = true
	end)
end

local function carLeave(st, bay, carInfo, oldHp, newHp)
	local car = carInfo.Model
	local plot = st.Plot
	if carInfo.Label then
		carInfo.Label.Text = ("✅ Getunt!\n%d → %d PS"):format(oldHp, newHp)
	end
	task.wait(1.5)
	if not car.Parent then
		bay.Car = nil
		return
	end
	animateLift(bay, 0, 2.2)
	carInfo.OnLift = false
	setCartText(bay, "OBD")
	-- Kunde steigt wieder ein
	if carInfo.Customer and carInfo.Customer.Parent and car.Parent then
		Npc.SeatInCar(carInfo.Customer, car)
		task.wait(0.6)
	end

	local function floorPos(x, z)
		return (plot.Origin * CFrame.new(x, 0.2 + CAR_HEIGHT, z)).Position
	end

	local front = lookCF(floorPos(bay.X, 12), -Vector3.zAxis)
	moveModel(car, bay.CF, front, 2.2)
	local exitX = bay.X

	if hasUpgrade(st, "Dyno") and not plot.DynoBusy then
		plot.DynoBusy = true
		local dynoCF = lookCF((plot.Origin * CFrame.new(DYNO_POS)).Position + Vector3.new(0, 0.8 + CAR_HEIGHT, 0), -Vector3.zAxis)
		moveModel(car, front, dynoCF, 2)
		local screen = plot.DynoScreen
		-- Rollen drehen hier; die Räder dreht jeder Client (Attribut DynoSpin)
		local spinning = {}
		if plot.Dyno then
			for _, d in ipairs(plot.Dyno:GetChildren()) do
				if d.Name == "Rolle" then
					table.insert(spinning, d)
				end
			end
		end
		exhaustSmoke(car, 3)
		local t0 = os.clock()
		local last = os.clock()
		local backfired = false
		while car.Parent and os.clock() - t0 < 3.2 do
			local now = os.clock()
			local dt = now - last
			last = now
			local a = math.clamp((now - t0) / 2.6, 0, 1)
			local hp = math.floor(oldHp + (newHp - oldHp) * a)
			local spin = (6 + 30 * a) * dt
			car:SetAttribute("DynoSpin", 6 + 30 * a)
			for _, sp in ipairs(spinning) do
				sp.CFrame = sp.CFrame * CFrame.Angles(-spin, 0, 0)
			end
			if screen and screen.Parent then
				screen.Text = ("PRÜFSTAND\n%d PS"):format(hp)
			end
			if carInfo.Label then
				carInfo.Label.Text = ("🔥 Prüfstand\n%d PS"):format(hp)
			end
			if a >= 1 and not backfired then
				backfired = true
				backfire(car, 0.8)
			end
			RunService.Heartbeat:Wait()
		end
		car:SetAttribute("DynoSpin", 0)
		if screen and screen.Parent then
			screen.Text = ("PRÜFSTAND\n%d PS ✔"):format(newHp)
		end
		front = dynoCF
		exitX = DYNO_POS.X
		plot.DynoBusy = false
	end

	local roadPos = (plot.Origin * CFrame.new(exitX, 0, ROAD_Z + 5)).Position + Vector3.new(0, CAR_HEIGHT + World.ROAD_TOP, 0)
	local onRoad = lookCF(roadPos, -Vector3.zAxis)
	moveModel(car, front, onRoad, 2.2)
	local turned = lookCF(roadPos, Vector3.xAxis)
	moveModel(car, onRoad, turned, 0.6)
	moveModel(car, turned, lookCF(roadPos + Vector3.new(160, 0, 0), Vector3.xAxis), 3)
	car:Destroy()
	bay.Car = nil
end

local function completeCar(player, st, bay, score, byAzubi)
	local carInfo = bay.Car
	if not carInfo or carInfo.Done then
		return
	end
	carInfo.Done = true
	carInfo.Ready = false
	carInfo.Busy = true
	local block = carInfo.Model:FindFirstChild("Kollision")
	if block then
		block.CanCollide = false
	end
	removeCable(carInfo)
	setCartText(bay, "✔ " .. Config.Stages[carInfo.Stage].Name)
	if bay.CartAttachment then
		playSound(bay.CartAttachment.Parent, "rbxasset://sounds/electronicpingshort.wav", 0.6)
	end
	if carInfo.Model.PrimaryPart then
		sparkle(carInfo.Model.PrimaryPart)
	end
	backfire(carInfo.Model, 1.2)
	if carInfo.Prompt then
		carInfo.Prompt:Destroy()
		carInfo.Prompt = nil
	end

	local def = carInfo.Def
	local stageDef = Config.Stages[carInfo.Stage]
	local quality = 0.5 + 0.5 * score
	local newHp = math.floor(def.Hp * (1 + stageDef.PowerGain * quality) + 0.5)
	local newNm = math.floor(def.Nm * (1 + stageDef.TorqueGain * quality) + 0.5)

	local mult = (0.4 + 0.6 * score) * def.PayMult * (1 + math.min(st.Data.Rep, 500) / 500)
	if hasUpgrade(st, "Dyno") then
		mult *= Config.DynoBonus
	end
	if hasPass(st, "DoubleMoney") then
		mult *= Config.DoubleMoneyMult
	end
	if hasPass(st, "VIP") then
		mult *= Config.VipMult
	end
	local pay = math.floor(stageDef.BasePay * mult)

	local repDelta
	if score >= 0.95 then
		repDelta = 3
	elseif score >= 0.55 then
		repDelta = 1
	else
		repDelta = -2
	end
	if byAzubi then
		repDelta = math.min(repDelta, 1)
	end

	setMoney(st, st.Data.Money + pay)
	setRep(st, math.max(0, st.Data.Rep + repDelta))
	st.Data.Tunes += 1

	if byAzubi then
		notify(player, ("🧑‍🔧 Azubi hat den %s getunt: +%s €"):format(def.Name, Config.Format(pay)), "good")
	else
		local tip = math.floor(pay * Config.TestDriveTip)
		st.LastTuned = { Def = def, Hp = newHp, Tip = tip, Expires = os.clock() + 120, Used = false }
		TuneResult:FireClient(player, {
			CanTestDrive = true,
			Tip = tip,
			CarName = def.Name,
			StageName = stageDef.Name,
			Hp = def.Hp,
			Nm = def.Nm,
			NewHp = newHp,
			NewNm = newNm,
			Pay = pay,
			RepDelta = repDelta,
			Score = score,
		})
	end

	task.spawn(carLeave, st, bay, carInfo, def.Hp, newHp)
end

startJob = function(player, st, bay, carInfo)
	if not carInfo.Ready or carInfo.Busy or carInfo.Done then
		return
	end
	if st.Job then
		notify(player, "Du tunst gerade schon ein Auto.", "bad")
		return
	end
	local stageDef = Config.Stages[carInfo.Stage]
	local width = hasUpgrade(st, "Laptop") and Config.ZoneWidthLaptop or Config.ZoneWidth
	local zones, speeds = {}, {}
	for r = 1, #Config.MapNames do
		zones[r] = 0.15 + math.random() * 0.7
		speeds[r] = (0.55 + 0.15 * (r - 1)) * stageDef.SpeedMult
	end
	jobCounter += 1
	st.Job = { Id = jobCounter, Bay = bay, Car = carInfo, Zones = zones, Width = width, Started = os.clock() }
	carInfo.Busy = true
	-- Bühne hoch, Diagnosekabel anschließen
	connectCable(bay, carInfo)
	setCartText(bay, "ECU lesen …")
	task.spawn(animateLift, bay, LIFT_UP, 2.5)

	local def = carInfo.Def
	OpenTuning:FireClient(player, {
		Id = jobCounter,
		CarName = def.Name,
		StageName = stageDef.Name,
		Hp = def.Hp,
		Nm = def.Nm,
		TargetHp = math.floor(def.Hp * (1 + stageDef.PowerGain) + 0.5),
		TargetNm = math.floor(def.Nm * (1 + stageDef.TorqueGain) + 0.5),
		Zones = zones,
		Width = width,
		Speeds = speeds,
		MapNames = Config.MapNames,
	})
end

FinishTuning.OnServerEvent:Connect(function(player, jobId, positions)
	local st = States[player]
	if not st or not st.Job or st.Job.Id ~= jobId or type(positions) ~= "table" then
		return
	end
	local job = st.Job
	st.Job = nil
	if os.clock() - job.Started < 1.5 or job.Bay.Car ~= job.Car then
		job.Car.Busy = false
		removeCable(job.Car)
		task.spawn(animateLift, job.Bay, 0, 2)
		return
	end
	local total = 0
	for r = 1, #job.Zones do
		local p = tonumber(positions[r])
		if p == nil or p ~= p then
			p = -1
		end
		p = math.clamp(p, -1, 2)
		total += Config.Score[Config.Rate(p, job.Zones[r], job.Width)]
	end
	completeCar(player, st, job.Bay, total / #job.Zones, false)
end)

CancelTuning.OnServerEvent:Connect(function(player, jobId)
	local st = States[player]
	if st and st.Job and st.Job.Id == jobId then
		local job = st.Job
		job.Car.Busy = false
		st.Job = nil
		removeCable(job.Car)
		setCartText(job.Bay, "OBD")
		task.spawn(animateLift, job.Bay, 0, 2)
	end
end)

------------------------------------------------------------------------
-- Shop
------------------------------------------------------------------------
BuyUpgrade.OnServerEvent:Connect(function(player, id)
	local st = States[player]
	if not st or not st.Plot or type(id) ~= "string" then
		return
	end
	local up = Config.GetUpgrade(id)
	if not up then
		return
	end
	if hasUpgrade(st, id) then
		notify(player, "Hast du schon.", "info")
		return
	end
	if up.Requires and not hasUpgrade(st, up.Requires) then
		notify(player, "Zuerst brauchst du: " .. Config.GetUpgrade(up.Requires).Name, "bad")
		return
	end
	if st.Data.Money < up.Price then
		notify(player, "Nicht genug Geld!", "bad")
		return
	end
	setMoney(st, st.Data.Money - up.Price)
	st.Data.Upgrades[id] = true
	player:SetAttribute("Upg_" .. id, true)

	local bayIndex = tonumber(id:match("^Bay(%d)$"))
	if bayIndex then
		local bay = st.Plot.Bays[bayIndex]
		if bay and bay.Lock then
			bay.Lock:Destroy()
			bay.Lock = nil
		end
	elseif id == "Dyno" then
		buildDyno(st.Plot, true)
	end
	notify(player, "✔ Gekauft: " .. up.Name, "good")
	saveData(player, st)
end)

------------------------------------------------------------------------
-- Fahren: Probefahrt und Firmenwagen
------------------------------------------------------------------------
local function getHumanoid(player)
	local char = player.Character
	return char and char:FindFirstChildOfClass("Humanoid"), char
end

local function teleportHome(player, st)
	local hum, char = getHumanoid(player)
	if hum and char and st.Plot then
		hum.Sit = false
		char:PivotTo(st.Plot.Origin * CFrame.new(0, 4, 28))
	end
end

local function endDrive(player, st, reason)
	local drive = st.Drive
	if not drive then
		return
	end
	st.Drive = nil
	local hum = getHumanoid(player)
	if hum and hum.SeatPart and hum.SeatPart:IsDescendantOf(drive.Car) then
		hum.Sit = false
	end
	drive.Car:Destroy()
	if drive.Mode == "test" then
		local driven = os.clock() - drive.Started
		if drive.Tip and drive.Tip > 0 and driven >= Config.TestDriveMinSeconds then
			setMoney(st, st.Data.Money + drive.Tip)
			notify(player, ("🏁 Der Kunde ist begeistert! Trinkgeld: +%s €"):format(Config.Format(drive.Tip)), "good")
		elseif reason == "time" then
			notify(player, "Die Zeit ist um – Probefahrt beendet.", "info")
		elseif reason ~= "silent" then
			notify(player, ("Probefahrt beendet. (Für Trinkgeld mindestens %d Sekunden fahren.)"):format(Config.TestDriveMinSeconds), "info")
		end
		task.delay(0.2, teleportHome, player, st)
	end
end

local function spawnDrivable(player, st, def, hp, cf, mode)
	endDrive(player, st, "silent")
	local car, seat = Cars.MakeDrivable(def)
	car:PivotTo(cf)
	seat:SetAttribute("Drivable", true)
	seat:SetAttribute("Hp", hp)
	seat:SetAttribute("Owner", player.UserId)
	seat:SetAttribute("Mode", mode)
	seat:SetAttribute("CarName", def.Name)
	local drive = { Car = car, Seat = seat, Mode = mode, Started = os.clock() }
	if mode == "test" then
		drive.Ends = os.clock() + Config.TestDriveSeconds
		seat:SetAttribute("EndsAt", workspace:GetServerTimeNow() + Config.TestDriveSeconds)
	end
	car.Parent = World.Vehicles
	st.Drive = drive
	pcall(function()
		car.PrimaryPart:SetNetworkOwner(player)
	end)

	seat:GetPropertyChangedSignal("Occupant"):Connect(function()
		local occ = seat.Occupant
		if occ then
			local who = Players:GetPlayerFromCharacter(occ.Parent)
			if who ~= player then
				-- Nur der Besitzer darf fahren
				local weld = seat:FindFirstChild("SeatWeld")
				if weld then
					weld:Destroy()
				end
				if who then
					notify(who, "Das ist nicht dein Auto!", "bad")
				end
				return
			end
			pcall(function()
				car.PrimaryPart:SetNetworkOwner(player)
			end)
		elseif mode == "test" and st.Drive == drive then
			task.delay(0.3, function()
				if st.Drive == drive and not seat.Occupant then
					endDrive(player, st)
				end
			end)
		end
	end)

	-- Spieler hineinsetzen
	local hum, char = getHumanoid(player)
	if hum and char and hum.Health > 0 then
		hum.Sit = false
		char:PivotTo(seat.CFrame + Vector3.new(0, 3, 0))
		task.wait(0.15)
		if seat.Parent and st.Drive == drive then
			seat:Sit(hum)
		end
	end
	return drive
end

RequestTestDrive.OnServerEvent:Connect(function(player)
	local st = States[player]
	if not st or not st.Plot then
		return
	end
	local lt = st.LastTuned
	if not lt or lt.Used or os.clock() > lt.Expires then
		notify(player, "Gerade ist keine Probefahrt möglich.", "bad")
		return
	end
	if st.Job then
		notify(player, "Erst das Tuning beenden.", "bad")
		return
	end
	lt.Used = true
	notify(player, "🏁 Probefahrt! Fahr eine Runde auf der Teststrecke (W/A/S/D).", "good")
	local drive = spawnDrivable(player, st, lt.Def, lt.Hp, World.TrackStart(st.Plot.Index), "test")
	drive.Tip = lt.Tip
end)

RequestCompanyCar.OnServerEvent:Connect(function(player)
	local st = States[player]
	if not st or not st.Plot then
		return
	end
	if st.Drive and st.Drive.Mode == "test" then
		notify(player, "Erst die Probefahrt beenden.", "bad")
		return
	end
	local now = os.clock()
	if st.LastCarRequest and now - st.LastCarRequest < 3 then
		return
	end
	st.LastCarRequest = now
	local hp = Config.CompanyCar.Hp + 120 * (maxStage(st) - 1)
	spawnDrivable(player, st, Config.CompanyCar, hp, st.Plot.CarSpot, "company")
end)

------------------------------------------------------------------------
-- Testen: Admin-Knöpfe (Studio, Besitzer des Spiels, Config.AdminUserIds)
------------------------------------------------------------------------
local function isAdmin(player)
	if RunService:IsStudio() then
		return true
	end
	if game.CreatorType == Enum.CreatorType.User and player.UserId == game.CreatorId then
		return true
	end
	return table.find(Config.AdminUserIds, player.UserId) ~= nil
end

AdminAction.OnServerEvent:Connect(function(player, action)
	local st = States[player]
	if not st or not isAdmin(player) then
		return
	end
	if action == "money" then
		setMoney(st, st.Data.Money + Config.AdminMoneyStep)
		notify(player, "🧪 Testgeld: +" .. Config.Format(Config.AdminMoneyStep) .. " €", "good")
	elseif action == "rep" then
		setRep(st, st.Data.Rep + Config.AdminRepStep)
		notify(player, "🧪 Ruf +" .. Config.AdminRepStep .. " (teurere Kundenautos)", "good")
	end
end)

EndDrive.OnServerEvent:Connect(function(player)
	local st = States[player]
	if not st or not st.Drive then
		return
	end
	if st.Drive.Mode == "test" then
		endDrive(player, st)
	else
		local hum = getHumanoid(player)
		if hum then
			hum.Sit = false
		end
	end
end)

------------------------------------------------------------------------
-- Robux-Shop (Game Passes und Developer Products)
------------------------------------------------------------------------
local GOLD = Color3.fromRGB(255, 200, 40)

local function vipTag(char)
	local head = char:WaitForChild("Head", 5)
	if not head or head:FindFirstChild("VipTag") then
		return
	end
	local bb = Instance.new("BillboardGui")
	bb.Name = "VipTag"
	bb.Size = UDim2.fromOffset(120, 30)
	bb.StudsOffset = Vector3.new(0, 2.6, 0)
	bb.MaxDistance = 80
	bb.Adornee = head
	local tl = Instance.new("TextLabel")
	tl.Size = UDim2.fromScale(1, 1)
	tl.BackgroundTransparency = 1
	tl.Font = Enum.Font.GothamBlack
	tl.TextScaled = true
	tl.TextColor3 = GOLD
	tl.TextStrokeTransparency = 0
	tl.Text = "⭐ VIP"
	tl.Parent = bb
	bb.Parent = head
end

local function applyPass(player, st, key)
	if st.Passes[key] then
		return
	end
	st.Passes[key] = true
	player:SetAttribute("Pass_" .. key, true)
	if key == "VIP" then
		local plot = st.Plot
		if plot and plot.SignLabel then
			plot.SignLabel.Text = "⭐ " .. player.DisplayName .. "s Chiptuning ⭐"
			plot.SignLabel.TextColor3 = GOLD
		end
		if plot and plot.Strip then
			plot.Strip.Color = GOLD
		end
		if player.Character then
			task.spawn(vipTag, player.Character)
		end
	end
end

local function checkPasses(player, st)
	for _, pass in ipairs(Config.GamePasses) do
		if pass.Id ~= 0 then
			local ok, owns = pcall(function()
				return MarketplaceService:UserOwnsGamePassAsync(player.UserId, pass.Id)
			end)
			if ok and owns and player.Parent then
				applyPass(player, st, pass.Key)
			end
		end
	end
end

MarketplaceService.PromptGamePassPurchaseFinished:Connect(function(player, passId, purchased)
	local st = States[player]
	if not purchased or not st then
		return
	end
	for _, pass in ipairs(Config.GamePasses) do
		if pass.Id ~= 0 and pass.Id == passId then
			applyPass(player, st, pass.Key)
			notify(player, "Danke! " .. pass.Name .. " ist jetzt aktiv.", "good")
		end
	end
end)

local function findProduct(id)
	for _, prod in ipairs(Config.Products) do
		if prod.Id ~= 0 and prod.Id == id then
			return prod
		end
	end
	return nil
end

-- Wird von Roblox für jeden Kauf eines Developer Products aufgerufen
MarketplaceService.ProcessReceipt = function(info)
	local player = Players:GetPlayerByUserId(info.PlayerId)
	local st = player and States[player]
	if not st then
		-- Spieler noch nicht geladen: Roblox versucht es später erneut
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end
	local receiptId = tostring(info.PurchaseId)
	if table.find(st.Data.Receipts, receiptId) then
		return Enum.ProductPurchaseDecision.PurchaseGranted
	end
	local prod = findProduct(info.ProductId)
	if not prod then
		warn("[Chiptuning] Unbekanntes Produkt: " .. tostring(info.ProductId))
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end

	setMoney(st, st.Data.Money + prod.Money)
	table.insert(st.Data.Receipts, receiptId)
	while #st.Data.Receipts > 50 do
		table.remove(st.Data.Receipts, 1)
	end
	if st.CanSave and not saveData(player, st) then
		-- Speichern fehlgeschlagen: zurücknehmen, Roblox versucht es später erneut
		setMoney(st, st.Data.Money - prod.Money)
		local i = table.find(st.Data.Receipts, receiptId)
		if i then
			table.remove(st.Data.Receipts, i)
		end
		return Enum.ProductPurchaseDecision.NotProcessedYet
	end
	notify(player, "Danke für deinen Kauf! +" .. Config.Format(prod.Money) .. " €", "good")
	return Enum.ProductPurchaseDecision.PurchaseGranted
end

------------------------------------------------------------------------
-- Spieler betreten / verlassen
------------------------------------------------------------------------
local function placeCharacter(player, char)
	local st = States[player]
	for _ = 1, 60 do
		if st and st.Plot then
			break
		end
		task.wait(0.25)
		st = States[player]
	end
	if not (st and st.Plot) then
		return
	end
	char:WaitForChild("HumanoidRootPart", 5)
	task.wait(0.1)
	if char.Parent then
		char:PivotTo(st.Plot.Origin * CFrame.new(0, 4, 28))
		if st.Passes.VIP then
			vipTag(char)
		end
	end
end

-- Avatare des Spielers und seiner Freunde als Fußgänger, Fahrer und Kunden
local FALLBACK_AVATARS = { 156, 261, 1 } -- bekannte Roblox-Konten als Reserve
local function collectAvatars(player)
	local ids = { player.UserId }
	pcall(function()
		local pages = Players:GetFriendsAsync(player.UserId)
		local friends = pages:GetCurrentPage()
		for i = 1, math.min(#friends, 14) do
			local j = math.random(i, #friends)
			friends[i], friends[j] = friends[j], friends[i]
			table.insert(ids, friends[i].Id)
		end
	end)
	for _, id in ipairs(FALLBACK_AVATARS) do
		table.insert(ids, id)
	end
	Npc.AddAvatars(ids, 24)
end

local function onPlayerAdded(player)
	task.spawn(collectAvatars, player)
	player.CharacterAdded:Connect(function(char)
		placeCharacter(player, char)
	end)

	local index = nil
	for i = 1, Config.MaxPlots do
		if not usedPlots[i] then
			index = i
			break
		end
	end
	if not index then
		player:Kick("Alle Werkstätten auf diesem Server sind belegt. Bitte einen anderen Server wählen.")
		return
	end
	usedPlots[index] = player

	local data, canSave = loadData(player)
	if not player.Parent then
		usedPlots[index] = nil
		return
	end

	local leaderstats = Instance.new("Folder")
	leaderstats.Name = "leaderstats"
	local money = Instance.new("IntValue")
	money.Name = "Geld"
	money.Value = data.Money
	money.Parent = leaderstats
	local rep = Instance.new("IntValue")
	rep.Name = "Ruf"
	rep.Value = data.Rep
	rep.Parent = leaderstats
	leaderstats.Parent = player

	for id in pairs(data.Upgrades) do
		player:SetAttribute("Upg_" .. id, true)
	end

	local st = {
		Data = data,
		CanSave = canSave,
		MoneyValue = money,
		RepValue = rep,
		Job = nil,
		Passes = {},
		NextCustomer = os.clock() + 3,
		NextAzubi = os.clock() + Config.AzubiInterval,
	}
	if isAdmin(player) then
		player:SetAttribute("Admin", true)
		if RunService:IsStudio() and st.Data.Money < Config.StudioMoney then
			setMoney(st, Config.StudioMoney)
			notify(player, "🧪 Studio-Test: Startgeld " .. Config.Format(Config.StudioMoney) .. " €", "good")
		end
	end
	st.Plot = buildPlot(player, st, index)
	States[player] = st
	task.spawn(checkPasses, player, st)

	if player.Character then
		task.spawn(placeCharacter, player, player.Character)
	end

	if not canSave then
		notify(player, "Hinweis: Speichern ist aus (in Studio: API-Zugriff erlauben).", "bad")
	end
	notify(player, "Willkommen in deiner Chiptuning-Werkstatt! 🔧", "good")
end

Players.PlayerAdded:Connect(onPlayerAdded)
for _, p in ipairs(Players:GetPlayers()) do
	task.spawn(onPlayerAdded, p)
end

Players.PlayerRemoving:Connect(function(player)
	local st = States[player]
	if not st then
		return
	end
	States[player] = nil
	if st.Drive then
		st.Drive.Car:Destroy()
		st.Drive = nil
	end
	saveData(player, st)
	if st.Plot then
		usedPlots[st.Plot.Index] = nil
		st.Plot.Model:Destroy()
	end
end)

game:BindToClose(function()
	for player, st in pairs(States) do
		task.spawn(saveData, player, st)
	end
	task.wait(3)
end)

------------------------------------------------------------------------
-- Hauptschleife: Kunden, Azubi, Autosave
------------------------------------------------------------------------
task.spawn(function()
	local lastSave = os.clock()
	while true do
		task.wait(1)
		local now = os.clock()
		for player, st in pairs(States) do
			if st.Plot then
				if now >= st.NextCustomer then
					for _, bay in ipairs(st.Plot.Bays) do
						if isBayUnlocked(st, bay.Index) and not bay.Car then
							spawnCustomer(player, st, bay)
							break
						end
					end
					local base = hasUpgrade(st, "Werbung") and Config.CustomerIntervalAds or Config.CustomerInterval
					if hasPass(st, "Turbo") then
						base *= Config.TurboMult
					end
					st.NextCustomer = now + base * (0.7 + math.random() * 0.6)
				end
				if st.Drive and st.Drive.Ends and now >= st.Drive.Ends then
					endDrive(player, st, "time")
				end
				if hasUpgrade(st, "Azubi") and now >= st.NextAzubi then
					st.NextAzubi = now + Config.AzubiInterval
					for _, bay in ipairs(st.Plot.Bays) do
						local c = bay.Car
						if c and c.Ready and not c.Busy and not c.Done then
							completeCar(player, st, bay, Config.Score.Good, true)
							break
						end
					end
				end
			end
		end
		if now - lastSave > 120 then
			lastSave = now
			for player, st in pairs(States) do
				task.spawn(saveData, player, st)
			end
		end
	end
end)

------------------------------------------------------------------------
-- Tag und Nacht
------------------------------------------------------------------------
task.spawn(function()
	local perSecond = 24 / (Config.DayLengthMinutes * 60)
	while true do
		local dt = task.wait(0.1)
		local t = Lighting.ClockTime
		local rate = (t < 6 or t > 19.5) and perSecond * 2 or perSecond -- Nächte gehen schneller vorbei
		Lighting.ClockTime = (t + rate * dt) % 24
	end
end)
