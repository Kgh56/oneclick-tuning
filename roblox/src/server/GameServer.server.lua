-- Chiptuning-Firma: Server
-- Script "GameServer" in ServerScriptService

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local DataStoreService = game:GetService("DataStoreService")
local Lighting = game:GetService("Lighting")
local HttpService = game:GetService("HttpService")
local CollectionService = game:GetService("CollectionService")
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
local Honk = newRemote("Honk") -- Client -> Server: Hupe
local ReportRecord = newRemote("ReportRecord") -- Client -> Server: Rekordversuch
local LevelUp = newRemote("LevelUp") -- Server -> Client
local DailyReward = newRemote("DailyReward") -- Server -> Client
local GarageAction = newRemote("GarageAction") -- Client -> Server
local Travel = newRemote("Travel") -- Client -> Server
local RaceJoin = newRemote("RaceJoin") -- Client -> Server
local RaceLap = newRemote("RaceLap") -- Client -> Server
local RaceGrid = newRemote("RaceGrid") -- Server -> Client: Startplatz
local SendFeedback = newRemote("SendFeedback") -- Client -> Server: Idee/Fehler
local FeedbackList = Instance.new("RemoteFunction") -- Client -> Server (nur Admins)
FeedbackList.Name = "FeedbackList"
FeedbackList.Parent = remotes
remotes.Parent = ReplicatedStorage

local function notify(player, text, kind)
	Notify:FireClient(player, text, kind or "info")
end

-- Sound am Server (alle hören ihn). key = Name aus Config.SoundSprite oder direkte ID
local EngineSound = require(ReplicatedStorage:WaitForChild("EngineSound"))
local function playSound(parent, key, volume, looped)
	if not parent then
		return nil
	end
	local snd
	if key:find("://") then
		snd = Instance.new("Sound")
		snd.SoundId = key
		snd.Looped = looped or false
		snd.Parent = parent
	else
		snd = EngineSound.Make(parent, key, looped)
	end
	if not snd then
		return nil
	end
	snd.Volume = volume or 0.7
	snd.RollOffMode = Enum.RollOffMode.InverseTapered
	snd.RollOffMinDistance = 10
	snd.RollOffMaxDistance = 160
	if not looped then
		snd:Play()
		task.delay(5, function()
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
	return {
		Money = Config.StartMoney,
		Rep = 0,
		Tunes = 0,
		Upgrades = {},
		Receipts = {},
		Records = {},
		Found = {},
		XP = 0,
		Daily = { Day = 0, Streak = 0 },
		Quests = { Day = 0, List = {} },
		Garage = { Owned = {}, Equip = {} },
	}
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
		if type(res.Records) == "table" then
			for k, v in pairs(res.Records) do
				if Config.Records[k] and tonumber(v) then
					data.Records[k] = tonumber(v)
				end
			end
		end
		if type(res.Found) == "table" then
			for _, id in ipairs(res.Found) do
				if type(id) == "number" then
					table.insert(data.Found, id)
				end
			end
		end
		data.XP = tonumber(res.XP) or 0
		if type(res.Daily) == "table" then
			data.Daily.Day = tonumber(res.Daily.Day) or 0
			data.Daily.Streak = tonumber(res.Daily.Streak) or 0
		end
		if type(res.Quests) == "table" and type(res.Quests.List) == "table" then
			data.Quests.Day = tonumber(res.Quests.Day) or 0
			data.Quests.List = res.Quests.List
		end
		if type(res.Garage) == "table" then
			if type(res.Garage.Owned) == "table" then
				for id, v in pairs(res.Garage.Owned) do
					if v == true and Config.GetGarageItem(id) then
						data.Garage.Owned[id] = true
					end
				end
			end
			if type(res.Garage.Equip) == "table" then
				for cat, id in pairs(res.Garage.Equip) do
					if type(id) == "string" and Config.GetGarageItem(id) then
						data.Garage.Equip[cat] = id
					end
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
			Records = st.Data.Records,
			Found = st.Data.Found,
			XP = st.Data.XP,
			Daily = st.Data.Daily,
			Quests = st.Data.Quests,
			Garage = st.Data.Garage,
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

------------------------------------------------------------------------
-- Fortschritt: Erfahrung/Level, Tagesaufträge, tägliche Belohnung
------------------------------------------------------------------------
local function today()
	return math.floor(os.time() / 86400)
end

local function syncProgress(player, st)
	local level, into, need = Config.LevelFromXP(st.Data.XP)
	player:SetAttribute("Level", level)
	player:SetAttribute("XPInto", into)
	player:SetAttribute("XPNeed", need)
	if st.LevelValue then
		st.LevelValue.Value = level
	end
end

local function addXP(player, st, amount)
	if amount <= 0 then
		return
	end
	local before = Config.LevelFromXP(st.Data.XP)
	st.Data.XP += amount
	local after = Config.LevelFromXP(st.Data.XP)
	if after > before then
		local reward = Config.LevelUpMoney * after
		setMoney(st, st.Data.Money + reward)
		LevelUp:FireClient(player, after, reward)
	end
	syncProgress(player, st)
end

local function syncQuests(player, st)
	player:SetAttribute("Quests", HttpService:JSONEncode(st.Data.Quests.List))
end

local function newQuests(st)
	local pool = table.clone(Config.QuestPool)
	local list = {}
	for _ = 1, 3 do
		local idx = math.random(1, #pool)
		local q = table.remove(pool, idx)
		local goal = math.random(q.Min, q.Max)
		if q.Id == "money" then
			goal = math.floor(goal / 500) * 500
		end
		table.insert(list, { Id = q.Id, Text = q.Text:format(goal), Goal = goal, Progress = 0, Done = false })
	end
	st.Data.Quests = { Day = today(), List = list }
end

-- Fortschritt melden: kind = "tune", "perfect", "jump", ... value = Menge oder Messwert
local function questEvent(player, st, kind, value)
	local changed = false
	local allBefore = true
	for _, q in ipairs(st.Data.Quests.List) do
		allBefore = allBefore and q.Done
	end
	for _, q in ipairs(st.Data.Quests.List) do
		if q.Id == kind and not q.Done then
			local def
			for _, d in ipairs(Config.QuestPool) do
				if d.Id == kind then
					def = d
				end
			end
			if def and def.Single then
				local ok = def.Lower and value <= q.Goal or (not def.Lower and value >= q.Goal)
				if ok then
					q.Progress = q.Goal
				end
			else
				q.Progress = math.min(q.Goal, q.Progress + (value or 1))
			end
			if q.Progress >= q.Goal then
				q.Done = true
				setMoney(st, st.Data.Money + Config.QuestReward)
				notify(player, ("📋 Auftrag erledigt: %s (+%s €)"):format(q.Text, Config.Format(Config.QuestReward)), "good")
				addXP(player, st, Config.XP.Quest)
			end
			changed = true
		end
	end
	if changed then
		local all = true
		for _, q in ipairs(st.Data.Quests.List) do
			all = all and q.Done
		end
		if all and not allBefore then
			setMoney(st, st.Data.Money + Config.QuestBonus)
			notify(player, ("🏆 Alle Tagesaufträge erledigt! Bonus +%s €"):format(Config.Format(Config.QuestBonus)), "good")
		end
		syncQuests(player, st)
	end
end


-- Garage: ausgewählte Teile des Firmenwagens
local function equipped(st, cat)
	local id = st.Data.Garage.Equip[cat] or Config.GarageDefaults[cat]
	return Config.GetGarageItem(id) or Config.GetGarageItem(Config.GarageDefaults[cat])
end

local function ownsItem(st, item)
	return item.Price == 0 or st.Data.Garage.Owned[item.Id] == true
end

local function syncGarage(player, st)
	local equip = {}
	for _, cat in ipairs(Config.GarageCats) do
		equip[cat] = equipped(st, cat).Id
	end
	player:SetAttribute("Garage", HttpService:JSONEncode({ Owned = st.Data.Garage.Owned, Equip = equip }))
end

local function companyDef(st)
	local neon = equipped(st, "Neon")
	return {
		Name = Config.CompanyCar.Name,
		Style = equipped(st, "Form").Style,
		Color = equipped(st, "Lack").Color,
		RimColor = equipped(st, "Felgen").Color,
		Underglow = neon.Color,
		Wing = equipped(st, "Flügel").Id == "fluegel_an",
		Hp = Config.CompanyCar.Hp,
		Nm = Config.CompanyCar.Nm,
	}
end

local function checkDaily(player, st)
	local day = today()
	if st.Data.Quests.Day ~= day or #st.Data.Quests.List == 0 then
		newQuests(st)
	end
	syncQuests(player, st)
	local d = st.Data.Daily
	if d.Day == day then
		return
	end
	d.Streak = (d.Day == day - 1) and (d.Streak + 1) or 1
	d.Day = day
	local idx = ((d.Streak - 1) % #Config.DailyRewards) + 1
	local reward = Config.DailyRewards[idx]
	setMoney(st, st.Data.Money + reward)
	addXP(player, st, Config.XP.Daily)
	DailyReward:FireClient(player, d.Streak, idx, reward, Config.DailyRewards)
end

-- Karosseriemitte über dem Boden (Ausstellungsautos)
local CAR_HEIGHT = Cars.BODY_HEIGHT

------------------------------------------------------------------------
-- Werkstatt (Grundstück)
------------------------------------------------------------------------
local function buildLock(plot, bay)
	-- Absperrung vor der Bühne: zwei Pfosten mit rot-weißer Kette und Schild
	local m = Instance.new("Model")
	m.Name = "Gesperrt"
	local z = BAY_Z + 14.5
	for _, dx in ipairs({ -5.5, 5.5 }) do
		for k = 0, 3 do
			part({
				Name = "Absperrpfosten",
				Size = Vector3.new(0.6, 0.9, 0.6),
				CFrame = plot.Origin * CFrame.new(bay.X + dx, 0.65 + k * 0.9, z),
				Color = (k % 2 == 0) and Color3.fromRGB(220, 30, 30) or Color3.new(1, 1, 1),
				CanCollide = false,
				Parent = m,
			})
		end
		part({ Name = "Pfostenfuss", Size = Vector3.new(1.4, 0.2, 1.4), CFrame = plot.Origin * CFrame.new(bay.X + dx, 0.32, z), Color = Color3.fromRGB(40, 40, 44), CanCollide = false, Parent = m })
	end
	for k = 0, 9 do
		part({
			Name = "Kette",
			Size = Vector3.new(1.1, 0.25, 0.25),
			CFrame = plot.Origin * CFrame.new(bay.X - 4.95 + k * 1.1, 2.9 - math.sin(k / 9 * math.pi) * 0.5, z),
			Color = (k % 2 == 0) and Color3.fromRGB(220, 30, 30) or Color3.new(1, 1, 1),
			CanCollide = false,
			Parent = m,
		})
	end
	local signPart = part({
		Name = "Sperrschild",
		Size = Vector3.new(4, 1.6, 0.15),
		CFrame = plot.Origin * CFrame.new(bay.X, 2.0, z + 0.2),
		Color = Color3.fromRGB(220, 30, 30),
		CanCollide = false,
		Parent = m,
	})
	textGui(signPart, Enum.NormalId.Back, "GESPERRT", Color3.new(1, 1, 1), Color3.fromRGB(220, 30, 30))
	m.Parent = plot.Model
	billboard(signPart, "🔒 Hebebühne " .. bay.Index .. "\nim Shop freischalten", 3)
	bay.Lock = m
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
	-- Werkstatt-Geräusche (Schlagschrauber, Klappern) leise in der Halle
	local ambience = playSound(backSign, "Werkstatt", 0.35, true)
	if ambience then
		ambience.RollOffMaxDistance = 70
		ambience:Play()
	end
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

	-- Büro-Ecke an der linken Wand (außerhalb der Fahrwege): Schreibtisch mit Laptop = Upgrade-Shop
	p({ Name = "Tisch", Size = Vector3.new(3.5, 0.4, 7), CFrame = at(-36, 3.2, 25), Color = Color3.fromRGB(110, 75, 50), Material = Enum.Material.Wood })
	for _, dz in ipairs({ -3.2, 3.2 }) do
		p({ Name = "Tischbein", Size = Vector3.new(3.2, 3, 0.3), CFrame = at(-36, 1.6, 25 + dz), Color = dark, Material = Enum.Material.Metal })
	end
	p({ Name = "Stuhl", Size = Vector3.new(2, 0.5, 2), CFrame = at(-33.2, 2, 25), Color = Color3.fromRGB(25, 25, 28), Material = Enum.Material.Fabric })
	p({ Name = "Lehne", Size = Vector3.new(0.4, 2.4, 2), CFrame = at(-32.2, 3.4, 25), Color = Color3.fromRGB(25, 25, 28), Material = Enum.Material.Fabric })
	local laptop = p({ Name = "Laptop", Size = Vector3.new(1.6, 0.15, 2.4), CFrame = at(-35.7, 3.48, 25), Color = Color3.fromRGB(30, 30, 35), Material = Enum.Material.Metal })
	local lid = p({ Name = "Bildschirm", Size = Vector3.new(0.1, 1.6, 2.4), CFrame = at(-36.6, 4.3, 25) * CFrame.Angles(0, 0, math.rad(12)), Color = Color3.fromRGB(30, 30, 35) })
	textGui(lid, Enum.NormalId.Right, "ECU", Color3.fromRGB(80, 200, 255), Color3.fromRGB(10, 20, 30))
	Util.light(lid, "SurfaceLight", { Face = Enum.NormalId.Right, Range = 6, Brightness = 1, Color = Color3.fromRGB(80, 200, 255) })
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

-- Punkt im Grundstück (lokal) -> Welt, y = Höhe der Karosseriemitte
local ROAD_Y = World.ROAD_TOP + CAR_HEIGHT
local FLOOR_Y = 0.2 + CAR_HEIGHT
local LIFT_Y = LIFT_TOP + CAR_HEIGHT
local DYNO_Y = 0.8 + CAR_HEIGHT
local LANE_Z = ROAD_Z + 5 -- rechte Fahrspur (ostwärts)

local function pts(plot, list)
	local out = {}
	for i, p in ipairs(list) do
		out[i] = (plot.Origin * CFrame.new(p[1], p[2], p[3])).Position
	end
	return out
end

-- Steht ein Spieler vor dem fahrenden Kundenauto?
local function playerInWay(pos, dir, range)
	for _, plr in ipairs(Players:GetPlayers()) do
		local char = plr.Character
		local hrp = char and char:FindFirstChild("HumanoidRootPart")
		if hrp then
			local rel = hrp.Position - pos
			local fwd = rel:Dot(dir)
			if fwd > -2 and fwd < (range or 14) and math.abs(rel.Y) < 7 and (rel - dir * fwd).Magnitude < 4.5 then
				return true
			end
		end
	end
	return false
end

local function driveOpts(car, opts)
	opts.Blocked = playerInWay
	opts.OnBlocked = function()
		if car.PrimaryPart then
			playSound(car.PrimaryPart, "Hupe", 0.6)
		end
	end
	return opts
end

-- In der Halle langsam, auf der Straße zügig
local function hallLimit(plot)
	return function(pos)
		local loc = plot.Origin:PointToObjectSpace(pos)
		if loc.Z < 2 then
			return 3.5 -- Rampe und Bühne
		elseif loc.Z < 34 then
			return 7 -- in der Halle
		end
		return nil
	end
end

-- Kunde steigt aus und geht zu seinem Warteplatz
local function customerGetsOut(plot, bay, customer, car)
	local door = plot.Origin * CFrame.new(bay.X - 4.6, 0.2, BAY_Z + 13.5)
	if car and car.PrimaryPart then
		playSound(car.PrimaryPart, "Tuer", 0.8)
	end
	local spot = plot.Origin * CFrame.new(bay.X - 7.4, 0.2, BAY_Z + 18)
	Npc.StandAt(customer, CFrame.lookAt(door.Position, spot.Position), plot.Model)
	task.wait(0.4)
	Npc.WalkTo(customer, spot.Position, 5.5)
	local hrp = customer.PrimaryPart
	if hrp then
		local carPos = (plot.Origin * CFrame.new(bay.X, 0, BAY_Z)).Position
		hrp.CFrame = CFrame.lookAt(hrp.Position, Vector3.new(carPos.X, hrp.Position.Y, carPos.Z))
	end
end

-- Kunde geht zur Fahrertür und steigt ein
local function customerGetsIn(plot, bay, customer, car)
	local door = plot.Origin * CFrame.new(bay.X - 4.6, 0.2, BAY_Z + 13.5)
	if customer.PrimaryPart and customer.PrimaryPart.Anchored then
		Npc.WalkTo(customer, door.Position, 5.5)
		task.wait(0.3)
	end
	Npc.SeatInCar(customer, car)
	if car.PrimaryPart then
		playSound(car.PrimaryPart, "Tuer", 0.8)
	end
	task.wait(0.5)
end

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
	local popBang = hasUpgrade(st, "PopBang") and math.random() < Config.PopBangChance
	local carInfo = { Def = def, Stage = stage, Model = car, Ready = false, Busy = false, Customer = customer, PopBang = popBang }
	bay.Car = carInfo

	local plot = st.Plot
	-- Anfahrt auf der rechten Spur, Linkskurve in die Einfahrt, langsam auf die Bühne
	local bx = bay.X
	local route = pts(plot, {
		{ bx - 170, ROAD_Y, LANE_Z },
		{ bx - 50, ROAD_Y, LANE_Z },
		{ bx - 16, ROAD_Y, LANE_Z - 2 },
		{ bx - 3, ROAD_Y + 0.05, 42 },
		{ bx, FLOOR_Y, 30 },
		{ bx, FLOOR_Y, 12 },
		{ bx, FLOOR_Y, BAY_Z + 13.2 },
		{ bx, LIFT_Y, BAY_Z + 9.4 },
		{ bx, LIFT_Y, BAY_Z },
	})
	car:PivotTo(CFrame.lookAt(route[1], route[2]))
	car.Parent = plot.Model

	task.spawn(function()
		Util.DrivePath(car, route, driveOpts(car, { Speed = 22, StartSpeed = 18, Limit = hallLimit(plot) }))
		if not car.Parent then
			return
		end
		car.PrimaryPart.CFrame = bay.CF
		task.wait(0.6)
		local stageDef = Config.Stages[stage]
		carInfo.Label = billboard(car.PrimaryPart, ("🚗 %s\nWunsch: %s%s · %d PS"):format(def.Name, stageDef.Name, popBang and " + Pop & Bang" or "", def.Hp), 5)

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
		-- Kunde steigt aus und geht zu seinem Warteplatz
		if customer then
			task.spawn(customerGetsOut, plot, bay, customer, car)
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
	-- Kunde geht zur Fahrertür und steigt ein
	if carInfo.Customer and carInfo.Customer.Parent and car.Parent then
		customerGetsIn(plot, bay, carInfo.Customer, car)
	end
	if not car.Parent then
		bay.Car = nil
		return
	end
	local bx = bay.X
	local limit = hallLimit(plot)

	if hasUpgrade(st, "Dyno") and not plot.DynoBusy then
		plot.DynoBusy = true
		local dx = DYNO_POS.X
		-- rückwärts von der Bühne, im Bogen vor den Prüfstand setzen
		Util.DrivePath(car, pts(plot, {
			{ bx, LIFT_Y, BAY_Z },
			{ bx, LIFT_Y, BAY_Z + 9.4 },
			{ bx, FLOOR_Y, BAY_Z + 13.2 },
			{ bx, FLOOR_Y, 6 },
			{ bx + (dx - bx) * 0.35, FLOOR_Y, 13 },
			{ bx + (dx - bx) * 0.8, FLOOR_Y, 20 },
			{ dx, FLOOR_Y, 26 },
			{ dx, FLOOR_Y, 32 },
		}), driveOpts(car, { Speed = 5, Reverse = true, Limit = limit }))
		task.wait(0.5)
		-- vorwärts langsam auf die Rollen
		Util.DrivePath(car, pts(plot, {
			{ dx, FLOOR_Y, 32 },
			{ dx, FLOOR_Y, 27 },
			{ dx, DYNO_Y, 22.5 },
			{ dx, DYNO_Y, DYNO_POS.Z },
		}), driveOpts(car, { Speed = 3 }))
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
				if carInfo.PopBang then
					task.delay(0.5, backfire, car, 0.6)
					task.delay(1.0, backfire, car, 0.6)
				end
			end
			RunService.Heartbeat:Wait()
		end
		car:SetAttribute("DynoSpin", 0)
		if screen and screen.Parent then
			screen.Text = ("PRÜFSTAND\n%d PS ✔"):format(newHp)
		end
		task.wait(0.8)
		plot.DynoBusy = false
		-- rückwärts vom Prüfstand im Bogen auf die Straße setzen
		Util.DrivePath(car, pts(plot, {
			{ dx, DYNO_Y, DYNO_POS.Z },
			{ dx, DYNO_Y, 22.5 },
			{ dx, FLOOR_Y, 28 },
			{ dx, FLOOR_Y, 36 },
			{ dx - 5, ROAD_Y, 44 },
			{ dx - 12, ROAD_Y, LANE_Z - 1 },
			{ dx - 22, ROAD_Y, LANE_Z },
		}), driveOpts(car, { Speed = 5, Reverse = true, Limit = limit }))
		bx = dx
	else
		-- rückwärts von der Bühne und im Bogen auf die Straße setzen
		Util.DrivePath(car, pts(plot, {
			{ bx, LIFT_Y, BAY_Z },
			{ bx, LIFT_Y, BAY_Z + 9.4 },
			{ bx, FLOOR_Y, BAY_Z + 13.2 },
			{ bx, FLOOR_Y, 20 },
			{ bx, FLOOR_Y, 34 },
			{ bx - 5, ROAD_Y, 44 },
			{ bx - 12, ROAD_Y, LANE_Z - 1 },
			{ bx - 22, ROAD_Y, LANE_Z },
		}), driveOpts(car, { Speed = 5, Reverse = true, Limit = limit }))
	end
	task.wait(0.5)
	-- vorwärts losfahren auf der rechten Spur
	Util.DrivePath(car, pts(plot, {
		{ bx - 22, ROAD_Y, LANE_Z },
		{ bx - 8, ROAD_Y, LANE_Z },
		{ bx + 60, ROAD_Y, LANE_Z },
		{ bx + 180, ROAD_Y, LANE_Z },
	}), driveOpts(car, { Speed = 26, EndSpeed = 26, Accel = 6 }))
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
		local customer = carInfo.Customer
		if customer and customer:GetAttribute("Pose") == "stand" then
			customer:SetAttribute("Pose", score >= 0.55 and "cheer" or "stand")
			task.delay(3, function()
				if customer.Parent and customer:GetAttribute("Pose") == "cheer" then
					customer:SetAttribute("Pose", "stand")
				end
			end)
		end
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
	if carInfo.PopBang then
		mult *= Config.PopBangPay
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
	-- Erfahrung und Tagesaufträge
	if byAzubi then
		addXP(player, st, Config.XP.Azubi)
	else
		addXP(player, st, Config.XP.Tune + Config.XP.TuneStage * carInfo.Stage + (score >= 0.95 and Config.XP.Perfect or 0))
		questEvent(player, st, "tune", 1)
		if score >= 0.95 then
			questEvent(player, st, "perfect", 1)
		end
	end
	questEvent(player, st, "money", pay)

	if byAzubi then
		notify(player, ("🧑‍🔧 Azubi hat den %s getunt: +%s €"):format(def.Name, Config.Format(pay)), "good")
	else
		local tip = math.floor(pay * Config.TestDriveTip)
		st.LastTuned = { Def = def, Hp = newHp, Tip = tip, Expires = os.clock() + 120, Used = false, PopBang = carInfo.PopBang }
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
	-- Drei von vier Minispielen in zufälliger Reihenfolge
	local pool = { "needle", "hold", "memory", "shift" }
	for i = #pool, 2, -1 do
		local j = math.random(1, i)
		pool[i], pool[j] = pool[j], pool[i]
	end
	local hard = stageDef.SpeedMult
	local games = {}
	for r = 1, 3 do
		local kind = pool[r]
		local g = { Type = kind, Width = width }
		if kind == "needle" then
			g.Name = "Zündzeitpunkt"
			g.Zone = 0.15 + math.random() * 0.7
			g.Speed = (0.6 + 0.12 * r) * hard
		elseif kind == "hold" then
			g.Name = "Ladedruck halten"
			g.Speed = 0.9 * hard
			g.Duration = 4
		elseif kind == "memory" then
			g.Name = "Fehlercodes löschen"
			g.Length = 3 + carInfo.Stage
			g.Seq = {}
			for k = 1, g.Length do
				g.Seq[k] = math.random(1, 4)
			end
		else
			g.Name = "Prüfstandslauf"
			g.Speed = 0.9 * hard
		end
		games[r] = g
	end
	jobCounter += 1
	st.Job = { Id = jobCounter, Bay = bay, Car = carInfo, Rounds = #games, Started = os.clock() }
	carInfo.Busy = true
	-- Bühne hoch, Diagnosekabel anschließen
	connectCable(bay, carInfo)
	setCartText(bay, "ECU lesen …")
	task.spawn(animateLift, bay, LIFT_UP, 2.5)
	task.delay(2.6, function()
		if bay.CartAttachment then
			playSound(bay.CartAttachment.Parent, "Schlagschrauber", 0.5)
		end
	end)

	local def = carInfo.Def
	OpenTuning:FireClient(player, {
		Id = jobCounter,
		CarName = def.Name,
		StageName = stageDef.Name,
		Hp = def.Hp,
		Nm = def.Nm,
		TargetHp = math.floor(def.Hp * (1 + stageDef.PowerGain) + 0.5),
		TargetNm = math.floor(def.Nm * (1 + stageDef.TorqueGain) + 0.5),
		Games = games,
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
	-- Jede Runde liefert 0..1; daraus wird Perfekt / Gut / Schlecht
	local total = 0
	for r = 1, job.Rounds do
		local sc = tonumber(positions[r])
		if sc == nil or sc ~= sc then
			sc = 0
		end
		sc = math.clamp(sc, 0, 1)
		local rating = (sc >= 0.8 and "Perfect") or (sc >= 0.45 and "Good") or "Bad"
		total += Config.Score[rating]
	end
	completeCar(player, st, job.Bay, total / job.Rounds, false)
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

-- Spieler im Auto ausblenden (das Dach bleibt zu); am Steuer sitzt eine Avatar-Kopie
local function setCharacterHidden(char, hidden)
	if not char then
		return
	end
	for _, d in ipairs(char:GetDescendants()) do
		if d:IsA("BasePart") or d:IsA("Decal") then
			if hidden then
				if d:GetAttribute("OrigT") == nil then
					d:SetAttribute("OrigT", d.Transparency)
				end
				d.Transparency = 1
			elseif d:GetAttribute("OrigT") ~= nil then
				d.Transparency = d:GetAttribute("OrigT")
				d:SetAttribute("OrigT", nil)
			end
		end
	end
end

local function addDriverDouble(player, car)
	local old = car:FindFirstChild("Fahrer")
	if old then
		old:Destroy()
	end
	local folder = ReplicatedStorage:FindFirstChild("Leute")
	local template = folder and folder:FindFirstChild("Avatar_" .. player.UserId)
	local person = template and template:Clone() or Npc.Random()
	if person then
		Npc.SeatInCar(person, car)
	end
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
	setCharacterHidden(player.Character, false)
	if drive.Mode == "test" then
		local driven = os.clock() - drive.Started
		if drive.Tip and drive.Tip > 0 and driven >= Config.TestDriveMinSeconds then
			setMoney(st, st.Data.Money + drive.Tip)
			addXP(player, st, Config.XP.TestDrive)
			questEvent(player, st, "testdrive", 1)
			notify(player, ("🏁 Der Kunde ist begeistert! Trinkgeld: +%s €"):format(Config.Format(drive.Tip)), "good")
		elseif reason == "time" then
			notify(player, "Die Zeit ist um – Probefahrt beendet.", "info")
		elseif reason ~= "silent" then
			notify(player, ("Probefahrt beendet. (Für Trinkgeld mindestens %d Sekunden fahren.)"):format(Config.TestDriveMinSeconds), "info")
		end
		task.delay(0.2, teleportHome, player, st)
	end
end

local function spawnDrivable(player, st, def, hp, cf, mode, popBang)
	endDrive(player, st, "silent")
	pcall(function()
		player:RequestStreamAroundAsync(cf.Position, 3) -- Umgebung vorladen (Streaming)
	end)
	local car, seat = Cars.MakeDrivable(def)
	car:PivotTo(cf)
	seat:SetAttribute("PopBang", popBang == true)
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
			setCharacterHidden(player.Character, true)
			addDriverDouble(player, car)
			return
		end
		-- ausgestiegen: Spieler wieder zeigen, Avatar-Kopie entfernen
		setCharacterHidden(player.Character, false)
		local double = car:FindFirstChild("Fahrer")
		if double then
			double:Destroy()
		end
		if mode == "test" and st.Drive == drive then
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
	local drive = spawnDrivable(player, st, lt.Def, lt.Hp, World.TrackStart(st.Plot.Index), "test", lt.PopBang)
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
	spawnDrivable(player, st, companyDef(st), hp, st.Plot.CarSpot, "company", hasUpgrade(st, "PopBang"))
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

Honk.OnServerEvent:Connect(function(player)
	local st = States[player]
	if not st or not st.Drive then
		return
	end
	local now = os.clock()
	if st.LastHonk and now - st.LastHonk < 0.6 then
		return
	end
	st.LastHonk = now
	playSound(st.Drive.Car.PrimaryPart, "Hupe", 0.9)
	player:SetAttribute("HonkAt", workspace:GetServerTimeNow())
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
-- Rekorde (Bestenliste über alle Server) und Schraubenschlüssel-Jagd
------------------------------------------------------------------------
local recordStores = {}
for kind in pairs(Config.Records) do
	pcall(function()
		recordStores[kind] = DataStoreService:GetOrderedDataStore("Rekord_" .. kind)
	end)
end
local sessionBest = {} -- [kind] = { {UserId, Name, Value}, ... }
local nameCache = {}
local boardDirty = true

-- Werte werden als ganze Zahlen gespeichert (Zehntel)
local function encode(_kind, v)
	return math.floor(v * 10 + 0.5)
end

local function formatValue(kind, v)
	local def = Config.Records[kind]
	if def.Unit == "s" then
		return ("%.2f s"):format(v)
	end
	return ("%d %s"):format(math.floor(v + 0.5), def.Unit)
end

local function better(kind, a, b)
	if b == nil then
		return true
	end
	if Config.Records[kind].Lower then
		return a < b
	end
	return a > b
end

local function updateBoards()
	local lines = { "🏆 REKORDE" }
	for _, kind in ipairs(Config.RecordOrder) do
		local def = Config.Records[kind]
		local top = {}
		local rstore = recordStores[kind]
		local ok = rstore and pcall(function()
			local pages = rstore:GetSortedAsync(def.Lower, 3)
			for _, entry in ipairs(pages:GetCurrentPage()) do
				local uid = tonumber(entry.key)
				local name = nameCache[uid]
				if not name then
					local okName, n = pcall(function()
						return Players:GetNameFromUserIdAsync(uid)
					end)
					name = okName and n or ("#" .. tostring(uid))
					nameCache[uid] = name
				end
				table.insert(top, { Name = name, Value = entry.value / 10 })
			end
		end)
		if not ok or #top == 0 then
			top = {}
			for i, e in ipairs(sessionBest[kind] or {}) do
				if i > 3 then
					break
				end
				table.insert(top, e)
			end
		end
		table.insert(lines, "")
		table.insert(lines, def.Name .. ":")
		if #top == 0 then
			table.insert(lines, "   – noch frei –")
		end
		for i, e in ipairs(top) do
			table.insert(lines, ("   %d. %s  %s"):format(i, e.Name, formatValue(kind, e.Value)))
		end
	end
	local text = table.concat(lines, "\n")
	for _, tl in ipairs(World.RecordBoards or {}) do
		tl.Text = text
	end
end

task.spawn(function()
	while true do
		if boardDirty then
			boardDirty = false
			updateBoards()
		end
		task.wait(15)
		boardDirty = boardDirty or (os.clock() % 120 < 15)
	end
end)

local LIMITS = { speed = { 20, 700 }, jump = { 3, 400 }, slalom = { 6, 300 }, lap = { 12, 600 } }

ReportRecord.OnServerEvent:Connect(function(player, kind, value)
	local st = States[player]
	value = tonumber(value)
	local lim = LIMITS[kind]
	if not st or not lim or not value or value ~= value or value < lim[1] or value > lim[2] then
		return
	end
	if not st.Drive then
		return -- nur aus dem Auto heraus
	end
	local def = Config.Records[kind]
	if kind == "jump" or kind == "speed" or kind == "slalom" then
		questEvent(player, st, kind, value)
	end
	-- Bestenliste dieser Sitzung
	local list = sessionBest[kind] or {}
	sessionBest[kind] = list
	local found = false
	for _, e in ipairs(list) do
		if e.UserId == player.UserId then
			found = true
			if better(kind, value, e.Value) then
				e.Value = value
			end
		end
	end
	if not found then
		table.insert(list, { UserId = player.UserId, Name = player.DisplayName, Value = value })
	end
	table.sort(list, function(a, b)
		return better(kind, a.Value, b.Value)
	end)
	-- Persönlicher Rekord?
	local old = st.Data.Records[kind]
	if better(kind, value, old) then
		st.Data.Records[kind] = value
		local now = os.clock()
		st.RecordRewardAt = st.RecordRewardAt or {}
		if not st.RecordRewardAt[kind] or now - st.RecordRewardAt[kind] > 30 then
			st.RecordRewardAt[kind] = now
			setMoney(st, st.Data.Money + def.Reward)
			addXP(player, st, Config.XP.Record)
			notify(player, ("🏆 Neuer persönlicher Rekord – %s: %s (+%s €)"):format(def.Name, formatValue(kind, value), Config.Format(def.Reward)), "good")
		end
		local rstore = recordStores[kind]
		if rstore and st.CanSave then
			task.spawn(pcall, function()
				rstore:SetAsync(tostring(player.UserId), encode(kind, value))
			end)
		end
		boardDirty = true
	end
end)

-- Goldene Schraubenschlüssel
local WRENCH_SPOTS = {
	Vector3.new(210, 0, -383), -- auf der Mega-Schanze
	Vector3.new(650, 0, 360), -- Steg am See
	Vector3.new(-120, 0, -205), -- Boxengasse
	Vector3.new(0, 0, -357), -- Tribüne
	Vector3.new(0, 0, 200), -- hinter den Läden
	Vector3.new(690, 0, -770), -- Landstraße Nordost
	Vector3.new(-690, 0, 250), -- Landstraße Südwest
	Vector3.new(-880, 0, -100), -- Feld West
	Vector3.new(880, 0, -300), -- Feld Ost
	Vector3.new(-400, 0, -700), -- Wiese Nordwest
	Vector3.new(300, 0, 500), -- Wiese Süd
	Vector3.new(-155, 0, -560), -- Slalom-Ziel
}
local wrenches = {}
do
	local wf = Instance.new("Folder")
	wf.Name = "Schraubenschluessel"
	wf.Parent = workspace
	for i, spot in ipairs(WRENCH_SPOTS) do
		local y = World.GroundY(spot.X, spot.Z)
		if i == 1 then
			y = 8.1 -- obere Kante der Mega-Schanze
		elseif i == 4 then
			y = 9 -- oberste Tribünenstufe
		end
		local pos = Vector3.new(spot.X, y + 3, spot.Z)
		local m = Instance.new("Model")
		m.Name = "Schluessel" .. i
		local handle = part({ Name = "Griff", Size = Vector3.new(0.6, 3.2, 0.3), CFrame = CFrame.new(pos), Color = Color3.fromRGB(255, 200, 40), Material = Enum.Material.Neon, CanCollide = false, Parent = m })
		part({ Name = "Maul", Size = Vector3.new(1.6, 0.9, 0.3), CFrame = CFrame.new(pos + Vector3.new(0, 1.8, 0)), Color = Color3.fromRGB(255, 200, 40), Material = Enum.Material.Neon, CanCollide = false, Parent = m })
		Util.light(handle, "PointLight", { Range = 14, Brightness = 2, Color = Color3.fromRGB(255, 200, 60) })
		m.PrimaryPart = handle
		m:SetAttribute("Id", i)
		m.Parent = wf
		CollectionService:AddTag(m, "Schluessel")
		wrenches[i] = pos
	end
end

local function syncFound(player, st)
	local ids = {}
	for _, id in ipairs(st.Data.Found) do
		table.insert(ids, tostring(id))
	end
	player:SetAttribute("Found", table.concat(ids, ","))
end

task.spawn(function()
	while true do
		task.wait(0.3)
		for player, st in pairs(States) do
			local char = player.Character
			local hrp = char and char:FindFirstChild("HumanoidRootPart")
			if hrp then
				for id, pos in pairs(wrenches) do
					if (hrp.Position - pos).Magnitude < 9 and not table.find(st.Data.Found, id) then
						table.insert(st.Data.Found, id)
						syncFound(player, st)
						local n = #st.Data.Found
						setMoney(st, st.Data.Money + Config.WrenchReward)
						addXP(player, st, Config.XP.Wrench)
						notify(player, ("🔧 Goldener Schraubenschlüssel %d/%d gefunden! +%s €"):format(n, #WRENCH_SPOTS, Config.Format(Config.WrenchReward)), "good")
						if n == #WRENCH_SPOTS then
							setMoney(st, st.Data.Money + Config.WrenchBonus)
							notify(player, ("🏆 Alle Schraubenschlüssel gefunden! Bonus +%s €"):format(Config.Format(Config.WrenchBonus)), "good")
						end
					end
				end
			end
		end
	end
end)

------------------------------------------------------------------------
-- Ideen-Briefkasten: Spieler schicken Ideen und Fehler, Admins lesen sie
------------------------------------------------------------------------
local TextService = game:GetService("TextService")
local feedbackStore
pcall(function()
	feedbackStore = DataStoreService:GetDataStore("ChiptuningFeedback_v1")
end)
local sessionFeedback = {}

SendFeedback.OnServerEvent:Connect(function(player, text)
	local st = States[player]
	if not st or type(text) ~= "string" then
		return
	end
	text = text:sub(1, 400)
	if #text:gsub("%s", "") < 3 then
		return
	end
	local now = os.clock()
	if st.LastFeedback and now - st.LastFeedback < 30 then
		notify(player, "Bitte warte kurz, bevor du noch eine Nachricht schickst.", "bad")
		return
	end
	st.LastFeedback = now
	-- Text durch den Roblox-Filter schicken
	local filtered = text
	pcall(function()
		local result = TextService:FilterStringAsync(text, player.UserId)
		filtered = result:GetNonChatStringForBroadcastAsync()
	end)
	local entry = { Name = player.Name, Text = filtered, Time = os.time(), Level = Config.LevelFromXP(st.Data.XP) }
	table.insert(sessionFeedback, 1, entry)
	if feedbackStore then
		task.spawn(pcall, function()
			feedbackStore:UpdateAsync("liste", function(old)
				old = type(old) == "table" and old or {}
				table.insert(old, 1, entry)
				while #old > 150 do
					table.remove(old)
				end
				return old
			end)
		end)
	end
	print(("[Feedback] %s: %s"):format(player.Name, filtered))
	notify(player, "💌 Danke für deine Idee! Wir lesen alles.", "good")
end)

FeedbackList.OnServerInvoke = function(player)
	if not player:GetAttribute("Admin") then
		return {}
	end
	local list
	if feedbackStore then
		pcall(function()
			list = feedbackStore:GetAsync("liste")
		end)
	end
	if type(list) ~= "table" or #list == 0 then
		list = sessionFeedback
	end
	return list
end

------------------------------------------------------------------------
-- Garage, Schnellreise, Rennen
------------------------------------------------------------------------
GarageAction.OnServerEvent:Connect(function(player, id)
	local st = States[player]
	local item = type(id) == "string" and Config.GetGarageItem(id)
	if not st or not item then
		return
	end
	if not ownsItem(st, item) then
		if st.Data.Money < item.Price then
			notify(player, "Nicht genug Geld!", "bad")
			return
		end
		setMoney(st, st.Data.Money - item.Price)
		st.Data.Garage.Owned[item.Id] = true
		notify(player, ("✔ Gekauft: %s (%s)"):format(item.Name, item.Cat), "good")
	end
	st.Data.Garage.Equip[item.Cat] = item.Id
	syncGarage(player, st)
	-- Firmenwagen neu bauen, falls er gerade steht
	if st.Drive and st.Drive.Mode == "company" then
		local hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
		local seated = hum and hum.SeatPart and hum.SeatPart:IsDescendantOf(st.Drive.Car)
		local cf = seated and st.Drive.Car.PrimaryPart.CFrame + Vector3.new(0, 0.3, 0) or st.Plot.CarSpot
		local hp = Config.CompanyCar.Hp + 120 * (maxStage(st) - 1)
		task.spawn(spawnDrivable, player, st, companyDef(st), hp, cf, "company", hasUpgrade(st, "PopBang"))
	end
end)

Travel.OnServerEvent:Connect(function(player, dest)
	local st = States[player]
	if not st or type(dest) ~= "string" then
		return
	end
	if st.Drive and st.Drive.Mode == "test" then
		notify(player, "Erst die Probefahrt beenden.", "bad")
		return
	end
	local now = os.clock()
	if st.LastTravel and now - st.LastTravel < 2 then
		return
	end
	st.LastTravel = now
	local target
	if dest == "werkstatt" then
		target = st.Plot.Origin.Position + Vector3.new(0, 4, 28)
	else
		for _, tp in ipairs(Config.TravelPoints) do
			if tp.Id == dest then
				target = tp.Pos
			end
		end
	end
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	if not target or not hum then
		return
	end
	hum.Sit = false
	pcall(function()
		player:RequestStreamAroundAsync(target, 3)
	end)
	task.wait(0.1)
	char:PivotTo(CFrame.new(target))
end)

-- Rennen auf der Teststrecke: beitreten im Auto, Countdown, 2 Runden, Preise
local Race = { Phase = "idle", Racers = {}, Order = {}, LobbyEnd = 0, StartAt = 0, Deadline = 0 }

local function notifyAll(text, kind)
	for _, plr in ipairs(Players:GetPlayers()) do
		notify(plr, text, kind)
	end
end

local function setRacePhase(phase)
	Race.Phase = phase
	ReplicatedStorage:SetAttribute("RacePhase", phase)
	ReplicatedStorage:SetAttribute("RaceStartAt", Race.StartAt)
	ReplicatedStorage:SetAttribute("RaceLaps", Config.RaceLaps)
end
setRacePhase("idle")

RaceJoin.OnServerEvent:Connect(function(player)
	local st = States[player]
	if not st or not st.Drive then
		notify(player, "Für ein Rennen musst du im Auto sitzen.", "bad")
		return
	end
	if Race.Phase == "running" or Race.Phase == "countdown" then
		notify(player, "Gerade läuft ein Rennen – gleich geht es wieder los!", "bad")
		return
	end
	if Race.Racers[player] then
		return
	end
	Race.Racers[player] = { Laps = 0, LastLap = 0 }
	player:SetAttribute("Racing", true)
	if Race.Phase == "idle" then
		Race.LobbyEnd = os.clock() + Config.RaceLobbySeconds
		Race.Order = {}
		setRacePhase("lobby")
		notifyAll(("🏁 %s startet ein Rennen! In %d s geht es los – im Auto auf „🏁 Rennen“ drücken."):format(player.DisplayName, Config.RaceLobbySeconds), "info")
	else
		notify(player, "🏁 Du bist dabei! Das Rennen startet gleich.", "good")
	end
end)

RaceLap.OnServerEvent:Connect(function(player, laps)
	local r = Race.Racers[player]
	local st = States[player]
	if not r or not st or Race.Phase ~= "running" or type(laps) ~= "number" then
		return
	end
	local now = os.clock()
	if laps ~= r.Laps + 1 or now - r.LastLap < 12 then
		return
	end
	r.Laps = laps
	r.LastLap = now
	if laps >= Config.RaceLaps and not r.Place then
		table.insert(Race.Order, player)
		r.Place = #Race.Order
		local prize = Config.RacePrizes[r.Place] or Config.RaceFinishPrize
		setMoney(st, st.Data.Money + prize)
		addXP(player, st, r.Place == 1 and Config.XP.RaceWin or Config.XP.RaceFinish)
		questEvent(player, st, "race", 1)
		local t = workspace:GetServerTimeNow() - Race.StartAt
		notifyAll(("🏁 %s: Platz %d in %.2f s (+%s €)"):format(player.DisplayName, r.Place, t, Config.Format(prize)), "good")
		if r.Place == 1 then
			Race.Deadline = math.min(Race.Deadline, os.clock() + 45)
		end
	end
end)

local function endRace()
	for plr in pairs(Race.Racers) do
		if plr.Parent then
			plr:SetAttribute("Racing", nil)
		end
	end
	Race.Racers = {}
	setRacePhase("idle")
end

task.spawn(function()
	while true do
		task.wait(0.25)
		local now = os.clock()
		if Race.Phase == "lobby" and now >= Race.LobbyEnd then
			local i = 0
			for plr in pairs(Race.Racers) do
				local st = States[plr]
				if plr.Parent and st and st.Drive then
					i += 1
					RaceGrid:FireClient(plr, World.TrackStart(i))
				else
					Race.Racers[plr] = nil
					if plr.Parent then
						plr:SetAttribute("Racing", nil)
					end
				end
			end
			if i == 0 then
				endRace()
			else
				Race.StartAt = workspace:GetServerTimeNow() + 4.5
				Race.Deadline = now + 4.5 + 240
				setRacePhase("countdown")
			end
		elseif Race.Phase == "countdown" and workspace:GetServerTimeNow() >= Race.StartAt then
			setRacePhase("running")
		elseif Race.Phase == "running" then
			local allDone = true
			for plr, r in pairs(Race.Racers) do
				local st = States[plr]
				if not plr.Parent or not st or not st.Drive then
					Race.Racers[plr] = nil
					if plr.Parent then
						plr:SetAttribute("Racing", nil)
					end
				elseif not r.Place then
					allDone = false
				end
			end
			if allDone or now >= Race.Deadline or next(Race.Racers) == nil then
				if #Race.Order > 0 then
					notifyAll(("🏆 Rennen beendet! Sieger: %s"):format(Race.Order[1].DisplayName), "good")
				end
				endRace()
			end
		end
	end
end)

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
	local levelValue = Instance.new("IntValue")
	levelValue.Name = "Level"
	levelValue.Value = Config.LevelFromXP(data.XP)
	levelValue.Parent = leaderstats
	leaderstats.Parent = player

	for id in pairs(data.Upgrades) do
		player:SetAttribute("Upg_" .. id, true)
	end

	local st = {
		Data = data,
		CanSave = canSave,
		MoneyValue = money,
		RepValue = rep,
		LevelValue = levelValue,
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
	syncFound(player, st)
	syncProgress(player, st)
	syncGarage(player, st)
	task.delay(3, function()
		if States[player] == st then
			checkDaily(player, st)
		end
	end)
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
		local night = t < 6 or t > 19.5
		local rate = night and perSecond * 3 or perSecond -- Nächte gehen schneller vorbei
		Lighting.ClockTime = (t + rate * dt) % 24
		-- Nachts heller (Mondlicht), damit man noch gut sieht
		local dark = 0
		if t > 18.5 then
			dark = math.clamp((t - 18.5) / 1.5, 0, 1)
		elseif t < 6.5 then
			dark = math.clamp((6.5 - t) / 1.5, 0, 1)
		end
		Lighting.OutdoorAmbient = Color3.fromRGB(125, 125, 135):Lerp(Color3.fromRGB(95, 105, 140), dark)
		Lighting.Ambient = Color3.fromRGB(45, 45, 52):Lerp(Color3.fromRGB(60, 65, 85), dark)
		Lighting.ExposureCompensation = 0.1 + 0.5 * dark
	end
end)
