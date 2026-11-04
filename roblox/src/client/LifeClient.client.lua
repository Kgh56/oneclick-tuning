-- Chiptuning-Firma: Leben in der Stadt
-- LocalScript "LifeClient" in StarterPlayer > StarterPlayerScripts
--
--  * dreht und lenkt die Räder aller Autos (Kunden, Verkehr, andere Spieler)
--  * bewegt Fahrer, wartende Kunden, Fußgänger und Zuschauer (Gelenke)
--  * Straßenverkehr und Fußgänger: laufen nur hier auf dem Client, aber für
--    alle Spieler gleich, weil alles aus der Serverzeit berechnet wird

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")
local CollectionService = game:GetService("CollectionService")

local player = Players.LocalPlayer
local Config = require(ReplicatedStorage:WaitForChild("Config"))
local Cars = require(ReplicatedStorage:WaitForChild("Cars"))
local Npc = require(ReplicatedStorage:WaitForChild("Npc"))
local Paths = require(ReplicatedStorage:WaitForChild("Paths"))
local EngineSound = require(ReplicatedStorage:WaitForChild("EngineSound"))
local SoundService = game:GetService("SoundService")
ReplicatedStorage:WaitForChild("Leute")

local ANIM_DISTANCE = 320 -- weiter entfernt wird nicht animiert

------------------------------------------------------------------------
-- Gelenke einer Person
------------------------------------------------------------------------
local jointCache = setmetatable({}, { __mode = "k" })

local function joints(person)
	local j = jointCache[person]
	if j then
		return j
	end
	j = {}
	for _, d in ipairs(person:GetDescendants()) do
		if d:IsA("Motor6D") then
			j[d.Name] = d
		end
	end
	jointCache[person] = j
	return j
end

local function setJ(j, name, cf)
	local m = j[name]
	if m then
		m.Transform = cf
	end
end

local rad = math.rad
local A = CFrame.Angles

-- Sitzen am Lenkrad; steer: Lenkwinkel (+ = links)
local function poseSit(person, steer, t, seed, reversing)
	local j = joints(person)
	-- Beine nach vorn zu den Pedalen (bleiben in der Karosserie)
	setJ(j, "LeftHip", A(rad(92), 0, 0))
	setJ(j, "RightHip", A(rad(92), 0, 0))
	setJ(j, "LeftKnee", A(rad(-22), 0, 0))
	setJ(j, "RightKnee", A(rad(-22), 0, 0))
	setJ(j, "LeftAnkle", A(rad(15), 0, 0))
	setJ(j, "RightAnkle", A(rad(15), 0, 0))
	local s = math.clamp(steer * 1.6, -0.5, 0.5)
	setJ(j, "LeftShoulder", A(rad(65) + s * 0.6, 0, rad(10)))
	setJ(j, "RightShoulder", A(rad(65) - s * 0.6, 0, rad(-10)))
	setJ(j, "LeftElbow", A(rad(25), 0, 0))
	setJ(j, "RightElbow", A(rad(25), 0, 0))
	-- Kopf: in die Kurve schauen, ab und zu umsehen
	local glance = math.sin(t * 0.7 + seed) * math.sin(t * 0.23 + seed * 2)
	if reversing then
		-- beim Rückwärtsfahren über die rechte Schulter nach hinten schauen
		setJ(j, "Neck", A(0, rad(-75), 0))
		setJ(j, "Waist", A(0, rad(-35), 0))
		setJ(j, "RightShoulder", A(rad(40), 0, rad(-50)))
	else
		setJ(j, "Neck", A(0, steer * 1.2 + glance * 0.5, 0))
		setJ(j, "Waist", A(0, 0, -steer * 0.15))
	end
end

local function poseStand(person, t, seed)
	local j = joints(person)
	for _, n in ipairs({ "LeftHip", "RightHip", "LeftKnee", "RightKnee", "LeftElbow", "RightElbow" }) do
		setJ(j, n, CFrame.new())
	end
	local breath = math.sin(t * 1.6 + seed) * 0.03
	setJ(j, "Waist", A(breath, 0, 0))
	setJ(j, "LeftShoulder", A(0, 0, rad(4) + breath))
	setJ(j, "RightShoulder", A(0, 0, rad(-4) - breath))
	setJ(j, "Neck", A(math.sin(t * 0.5 + seed) * 0.1, math.sin(t * 0.3 + seed) * 0.6, 0))
end

local function poseWalk(person, phase)
	local j = joints(person)
	local s = math.sin(phase)
	local c = math.cos(phase)
	setJ(j, "LeftHip", A(s * 0.55, 0, 0))
	setJ(j, "RightHip", A(-s * 0.55, 0, 0))
	setJ(j, "LeftKnee", A(-math.max(0, -c) * 0.8, 0, 0))
	setJ(j, "RightKnee", A(-math.max(0, c) * 0.8, 0, 0))
	setJ(j, "LeftShoulder", A(-s * 0.45, 0, rad(4)))
	setJ(j, "RightShoulder", A(s * 0.45, 0, rad(-4)))
	setJ(j, "LeftElbow", A(rad(15), 0, 0))
	setJ(j, "RightElbow", A(rad(15), 0, 0))
	setJ(j, "Waist", A(0, s * 0.08, 0))
	setJ(j, "Neck", A(0, -s * 0.05, 0))
end

local function poseCheer(person, t, seed)
	local j = joints(person)
	local wave = math.sin(t * 6 + seed) * 0.35
	local up = (math.sin(t * 0.8 + seed) > 0.3) and 1 or 0
	setJ(j, "LeftShoulder", A(rad(-30) * (1 - up) + rad(-160) * up + wave * up, 0, rad(10)))
	setJ(j, "RightShoulder", A(rad(-30) * (1 - up) + rad(-160) * up - wave * up, 0, rad(-10)))
	setJ(j, "LeftElbow", A(rad(20), 0, 0))
	setJ(j, "RightElbow", A(rad(20), 0, 0))
	setJ(j, "Neck", A(0, math.sin(t * 0.9 + seed) * 0.7, 0))
	setJ(j, "Waist", A(0, 0, math.sin(t * 3 + seed) * 0.04 * up))
end

------------------------------------------------------------------------
-- Echte Animationen: dieselben wie beim eigenen Charakter
------------------------------------------------------------------------
-- Standard-Animationen von Roblox (R15). Werden durch die Animationen des
-- eigenen Charakters ersetzt, damit alle genauso laufen wie du.
local ANIMS = {
	walk = "rbxassetid://507777826",
	idle = "rbxassetid://507766666",
	cheer = "rbxassetid://507770677",
	wave = "rbxassetid://507770239",
}
local animsReady = false

task.spawn(function()
	local char = player.Character or player.CharacterAdded:Wait()
	local animate = char:WaitForChild("Animate", 8)
	if animate then
		for _, kind in ipairs({ "walk", "idle", "cheer", "wave" }) do
			local folder = animate:FindFirstChild(kind)
			local anim = folder and folder:FindFirstChildOfClass("Animation")
			if anim and anim.AnimationId ~= "" then
				ANIMS[kind] = anim.AnimationId
			end
		end
	end
	animsReady = true
end)

local trackCache = setmetatable({}, { __mode = "k" })

local function getAnimator(person)
	local hum = person:FindFirstChildOfClass("Humanoid")
	if not hum then
		return nil
	end
	local an = hum:FindFirstChildOfClass("Animator")
	if not an then
		an = Instance.new("Animator")
		an.Parent = hum
	end
	return an
end

-- Spielt eine Animation in Schleife (nil = alle stoppen). Gibt true zurück, wenn sie läuft.
local function playAnim(person, kind, speed)
	local cache = trackCache[person]
	if not cache then
		cache = { Tracks = {} }
		trackCache[person] = cache
	end
	if cache.Current == kind then
		local tr = kind and cache.Tracks[kind]
		if tr and speed then
			tr:AdjustSpeed(speed)
		end
		return tr ~= nil
	end
	for _, tr in pairs(cache.Tracks) do
		if tr.IsPlaying then
			tr:Stop(0.25)
		end
	end
	cache.Current = kind
	if not kind or not animsReady then
		cache.Current = nil
		return false
	end
	local tr = cache.Tracks[kind]
	if not tr and not cache.Failed then
		local an = getAnimator(person)
		local anim = Instance.new("Animation")
		anim.AnimationId = ANIMS[kind]
		local ok, res = pcall(function()
			return an:LoadAnimation(anim)
		end)
		if ok and res then
			tr = res
			tr.Looped = true
			cache.Tracks[kind] = tr
		else
			cache.Failed = true
		end
	end
	if not tr then
		return false
	end
	tr:Play(0.25)
	if speed then
		tr:AdjustSpeed(speed)
	end
	return true
end

------------------------------------------------------------------------
-- Räder und Fahrer aller Autos
------------------------------------------------------------------------
local carState = setmetatable({}, { __mode = "k" })

local function myCar()
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	return seat and seat.Parent
end

local SOUND_DISTANCE = 170
local lightOverride = setmetatable({}, { __mode = "k" }) -- Verkehr setzt Blinker/Bremse selbst

local function dropSound(st)
	if st and st.Sound then
		st.Sound:Destroy()
		st.Sound = nil
	end
end

local function animateCar(car, dt, now, camPos, mine)
	local root = car.PrimaryPart
	if not root then
		return
	end
	local isMine = car == mine
	if isMine then
		dropSound(carState[car]) -- das eigene Auto klingt und leuchtet über DriveClient
	end
	local pos = root.Position
	if (pos - camPos).Magnitude > ANIM_DISTANCE then
		local st = carState[car]
		if st then
			st.LastPos = pos
			st.LastLook = root.CFrame.LookVector
			dropSound(st)
		end
		return
	end
	local st = carState[car]
	if not st then
		st = { LastPos = pos, LastLook = root.CFrame.LookVector, Spin = 0, Steer = 0, Motors = {}, Seed = math.random() * 10 }
		for _, m in ipairs(root:GetChildren()) do
			if m:IsA("Motor6D") then
				if m.Name:sub(1, 3) == "Rad" then
					table.insert(st.Motors, m)
				elseif m.Name == "LenkradMotor" then
					st.Steering = m
				end
			end
		end
		carState[car] = st
	end
	local look = root.CFrame.LookVector
	local v = (pos - st.LastPos):Dot(look) / math.max(dt, 1e-3)
	if math.abs(v) > 400 then
		v = 0 -- Teleport
	end
	local cross = st.LastLook:Cross(look).Y
	local yawRate = math.asin(math.clamp(cross, -1, 1)) / math.max(dt, 1e-3)
	st.LastPos = pos
	st.LastLook = look
	local target = 0
	if math.abs(v) > 0.5 then
		target = math.clamp(math.atan(yawRate * 8 / math.max(math.abs(v), 3)) * (v >= 0 and 1 or -1), -0.6, 0.6)
	end
	st.Steer += (target - st.Steer) * math.min(1, dt * 8)
	local dyno = car:GetAttribute("DynoSpin") or 0
	st.Spin = (st.Spin - (v / Cars.WHEEL_RADIUS + dyno) * dt) % (math.pi * 2)
	if not isMine then
		for _, m in ipairs(st.Motors) do
			m.Transform = A(0, m:GetAttribute("Front") and st.Steer or 0, 0) * A(st.Spin, 0, 0)
		end
		if st.Steering then
			st.Steering.Transform = A(-st.Steer * 4, 0, 0)
		end
	end
	-- Brems- und Blinklichter
	if car.Name ~= "Geparkt" and not isMine then
		st.Lights = st.Lights or Cars.LightParts(car)
		st.Acc = (st.Acc or 0) + (((v - (st.LastVL or v)) / math.max(dt, 1e-3)) - (st.Acc or 0)) * math.min(1, dt * 5)
		st.LastVL = v
		local ov = lightOverride[car]
		local braking, blink
		if ov then
			braking, blink = ov.Braking, ov.Blink
		else
			braking = st.Acc < -3 or (math.abs(v) < 0.3 and (st.Still or 0) < 1.2)
			blink = (math.abs(st.Steer) > 0.2 and math.abs(v) < 25) and (st.Steer > 0 and -1 or 1) or 0
		end
		Cars.SetLights(st.Lights, braking, blink, now)
	end

	local driver = car:FindFirstChild("Fahrer")
	if driver then
		local cache = trackCache[driver]
		if cache and cache.Current then
			playAnim(driver, nil)
		end
		st.Rev = (st.Rev or 0) + ((v < -0.4 and 1 or 0) - (st.Rev or 0)) * math.min(1, dt * 6)
		poseSit(driver, st.Steer, now, st.Seed, st.Rev > 0.5)
	end

	-- Motorgeräusch
	local dist = (pos - camPos).Magnitude
	if isMine or car.Name == "Geparkt" or dist > SOUND_DISTANCE + 30 then
		dropSound(st)
		return
	end
	local seat = car:FindFirstChild("Fahrersitz")
	local moving = math.abs(v) > 0.3
	st.Still = moving and 0 or (st.Still or 0) + dt
	local running
	if dyno > 0 or car.Name == "Verkehr" then
		running = true
	elseif seat then
		running = seat.Occupant ~= nil
	else
		running = st.Still < 1.5
	end
	if not running then
		dropSound(st)
		return
	end
	if dist < SOUND_DISTANCE and not st.Sound then
		st.Sound = EngineSound.new(root, car.Name == "Verkehr" and 0.45 or 0.8, false)
		st.Rpm = EngineSound.IDLE
		st.LastV = v
	end
	if st.Sound then
		local accel = (v - (st.LastV or v)) / math.max(dt, 1e-3)
		st.LastV = v
		st.Load = (st.Load or 0.3) + (math.clamp(0.3 + accel / 12, 0.15, 1) - (st.Load or 0.3)) * math.min(1, dt * 4)
		local rpmTarget
		if dyno > 0 then
			rpmTarget = 1500 + math.min(dyno / 36, 1) * 5200
			st.Load = 1
		else
			rpmTarget = EngineSound.Rpm(v, 120)
		end
		st.Rpm += (rpmTarget - st.Rpm) * math.min(1, dt * 6)
		st.Sound:Update(st.Rpm, st.Load, 0, 0)
	end
end

------------------------------------------------------------------------
-- Straßenverkehr
------------------------------------------------------------------------
local lifeFolder = Instance.new("Folder")
lifeFolder.Name = "Stadtleben"
lifeFolder.Parent = workspace

local STYLES = { "hatch", "hatch", "sedan", "sedan", "wagon", "coupe", "super" }
local COLORS = {
	Color3.fromRGB(235, 235, 238), Color3.fromRGB(25, 25, 28), Color3.fromRGB(120, 125, 132),
	Color3.fromRGB(170, 20, 30), Color3.fromRGB(25, 60, 140), Color3.fromRGB(30, 90, 60),
	Color3.fromRGB(200, 200, 205), Color3.fromRGB(240, 170, 0), Color3.fromRGB(90, 40, 30),
	Color3.fromRGB(60, 120, 190),
}

local traffic = {}
do
	local rng = Random.new(2002)
	local loops = Paths.TrafficLoops
	local total = 0
	for _, l in ipairs(loops) do
		total += l.Length
	end
	for li, loop in ipairs(loops) do
		local n = math.max(1, math.floor(Config.TrafficCars * loop.Length / total + 0.5))
		for i = 1, n do
			local def = {
				Name = "Verkehr",
				Style = STYLES[rng:NextInteger(1, #STYLES)],
				Hp = rng:NextInteger(90, 320),
				Color = COLORS[rng:NextInteger(1, #COLORS)],
			}
			local car = Cars.MakeShowCar(def)
			car.Kollision.CanCollide = true
			local person = Npc.Random(rng)
			if person then
				Npc.SeatInCar(person, car)
			end
			car.Parent = lifeFolder
			table.insert(traffic, {
				Car = car,
				Root = car.PrimaryPart,
				Path = loop,
				S = (i - 1) / n * loop.Length + li * 37,
				V = 0,
				LastV = 0,
				Acc = 0,
				Cruise = Config.TrafficSpeed * rng:NextNumber(0.85, 1.1),
				Blink = 0,
				Braking = false,
			})
		end
	end
end

------------------------------------------------------------------------
-- Fußgänger und Zuschauer
------------------------------------------------------------------------
local walkers = {}
local spectators = {}
do
	local rng = Random.new(77)
	local ways = Paths.Walkways
	for i = 1, Config.Pedestrians do
		local way = ways[(i - 1) % #ways + 1]
		local person = Npc.Random(rng)
		if person then
			person.Parent = lifeFolder
			table.insert(walkers, {
				Person = person,
				Root = person.PrimaryPart,
				Way = way,
				Speed = rng:NextNumber(6.5, 9),
				Phase = rng:NextNumber(0, 1000),
				Foot = Npc.Dim(person, "FootOffset", 3),
			})
		end
	end
	for _, cf in ipairs(Paths.Spectators()) do
		local person = Npc.Random(rng)
		if person then
			person.PrimaryPart.CFrame = cf * CFrame.new(0, Npc.Dim(person, "FootOffset", 3), 0)
			person.Parent = lifeFolder
			table.insert(spectators, { Person = person, Seed = rng:NextNumber(0, 10), CF = cf })
		end
	end
end

-- Sobald echte Avatare (du und deine Freunde) geladen sind, die Puppen ersetzen
do
	local leute = ReplicatedStorage:WaitForChild("Leute")
	local pending = false
	local rng = Random.new(99)
	local function swapAll()
		pending = false
		if Npc.AvatarCount() < 3 then
			return
		end
		for _, w in ipairs(walkers) do
			if not w.Person:GetAttribute("Avatar") then
				local person = Npc.Random(rng)
				if person and person:GetAttribute("Avatar") then
					w.Person:Destroy()
					person.Parent = lifeFolder
					w.Person = person
					w.Root = person.PrimaryPart
					w.Foot = Npc.Dim(person, "FootOffset", 3)
				end
			end
		end
		for _, sp in ipairs(spectators) do
			if not sp.Person:GetAttribute("Avatar") then
				local person = Npc.Random(rng)
				if person and person:GetAttribute("Avatar") then
					sp.Person:Destroy()
					person.PrimaryPart.CFrame = sp.CF * CFrame.new(0, Npc.Dim(person, "FootOffset", 3), 0)
					person.Parent = lifeFolder
					sp.Person = person
				end
			end
		end
		for _, tc in ipairs(traffic) do
			local old = tc.Car:FindFirstChild("Fahrer")
			if old and not old:GetAttribute("Avatar") then
				local person = Npc.Random(rng)
				if person and person:GetAttribute("Avatar") then
					old:Destroy()
					Npc.SeatInCar(person, tc.Car)
				end
			end
		end
	end
	leute.ChildAdded:Connect(function(t)
		if t:GetAttribute("Avatar") and not pending then
			pending = true
			task.delay(3, swapAll)
		end
	end)
	task.delay(4, swapAll)
end

-- Umgebungsgeräusch (Wind und Vögel)
do
	local amb = EngineSound.Make(SoundService, "Umgebung", true)
	if amb then
		amb.Volume = 0.35
		amb:Play()
	end
end

local function pingpong(u)
	local m = u % 2
	return (m < 1) and m or (2 - m), (m < 1) and 1 or -1
end

------------------------------------------------------------------------
-- Hauptschleife
------------------------------------------------------------------------
local function referencePos()
	local mine = myCar()
	if mine and mine.PrimaryPart then
		return mine.PrimaryPart.Position, mine
	end
	local char = player.Character
	local hrp = char and char:FindFirstChild("HumanoidRootPart")
	return hrp and hrp.Position or nil, nil
end

-- Richtung entlang des Weges (geglättet)
local function sampleDir(path, s)
	local pos = Paths.Sample(path, s)
	local a = Paths.Sample(path, s + 4)
	local b = Paths.Sample(path, s - 4)
	local d = a - b
	return pos, (d.Magnitude > 0.01) and d.Unit or Vector3.xAxis
end

-- Bodenhöhe unter einem Punkt messen (Gelände, Gehwege, Straßen)
local groundParams = RaycastParams.new()
groundParams.FilterType = Enum.RaycastFilterType.Exclude
local function groundAt(pos, fallback)
	local ignore = { lifeFolder }
	if player.Character then
		table.insert(ignore, player.Character)
	end
	local vehicles = workspace:FindFirstChild("Fahrzeuge")
	if vehicles then
		table.insert(ignore, vehicles)
	end
	groundParams.FilterDescendantsInstances = ignore
	local hit = workspace:Raycast(Vector3.new(pos.X, pos.Y + 25, pos.Z), Vector3.new(0, -60, 0), groundParams)
	return hit and hit.Position.Y or fallback
end

local BRAKE = 24 -- Bremsverzögerung Verkehr
local ACCEL = 9 -- Anfahren Verkehr
local obstacles = {}

local function updateTraffic(dt, now, me)
	-- Hindernisse sammeln: Verkehr, andere Autos, der Spieler
	table.clear(obstacles)
	for _, tc in ipairs(traffic) do
		table.insert(obstacles, { Pos = tc.Root.Position, Car = tc.Car })
	end
	for _, car in ipairs(CollectionService:GetTagged(Cars.TAG)) do
		if car.Name ~= "Verkehr" and car.PrimaryPart and car:IsDescendantOf(workspace) then
			table.insert(obstacles, { Pos = car.PrimaryPart.Position, Car = car })
		end
	end
	if me then
		-- Spieler: etwas mehr Abstand halten
		table.insert(obstacles, { Pos = me, Extra = 4 })
	end

	for _, tc in ipairs(traffic) do
		local pos, dir = sampleDir(tc.Path, tc.S)
		local target = tc.Cruise

		-- Kurve voraus: langsamer und blinken
		local _, dirAhead = sampleDir(tc.Path, tc.S + 28)
		local angle = math.acos(math.clamp(dir:Dot(dirAhead), -1, 1))
		if angle > 0.35 then
			target = math.min(target, 15)
			tc.Blink = (dir:Cross(dirAhead).Y > 0) and -1 or 1
		else
			local _, dirFar = sampleDir(tc.Path, tc.S + 60)
			local far = math.acos(math.clamp(dir:Dot(dirFar), -1, 1))
			tc.Blink = (far > 0.35) and ((dir:Cross(dirFar).Y > 0) and -1 or 1) or 0
		end

		-- Abstand zum Vordermann halten
		local nearest = math.huge
		local blockedByMe = false
		for _, ob in ipairs(obstacles) do
			if ob.Car ~= tc.Car then
				local to = ob.Pos - pos
				local fwd = to:Dot(dir)
				if fwd > 0 and fwd < 50 and math.abs(to.Y) < 8 then
					local side = (to - dir * fwd).Magnitude
					if side < 3.6 and fwd - (ob.Extra or 0) < nearest then
						nearest = fwd - (ob.Extra or 0)
						blockedByMe = ob.Extra ~= nil and fwd < 30
					end
				end
			end
		end
		if nearest < math.huge then
			local free = nearest - 13
			target = math.min(target, math.sqrt(math.max(0, 2 * BRAKE * 0.7 * free)))
		end

		-- Ampeln
		for _, c in ipairs(Paths.Intersections) do
			local to = c - pos
			local along = to:Dot(dir)
			local lateral = (to - dir * along).Magnitude
			if along > 13 and along < 70 and lateral < 14 then
				local axis = math.abs(dir.X) > math.abs(dir.Z) and "EW" or "NS"
				local state = Paths.LightState(axis, now)
				if state ~= "green" then
					local stopDist = along - 16
					local canStop = tc.V * tc.V / (2 * BRAKE) < stopDist + 2
					if state == "red" or canStop then
						target = math.min(target, math.sqrt(math.max(0, 2 * BRAKE * 0.6 * math.max(0, stopDist))))
					end
				end
			end
		end

		-- Spieler steht im Weg: kurz anhupen
		if blockedByMe and tc.V < 3 then
			tc.BlockedFor = (tc.BlockedFor or 0) + dt
			if tc.BlockedFor > 0.8 and not tc.Honked then
				tc.Honked = true
				EngineSound.OneShot(tc.Root, "Hupe", 0.6)
			end
		elseif not blockedByMe then
			tc.BlockedFor = 0
			tc.Honked = false
		end

		-- Gas geben / bremsen
		if tc.V < target then
			tc.V = math.min(target, tc.V + ACCEL * dt)
		else
			tc.V = math.max(target, tc.V - BRAKE * dt)
		end
		tc.Braking = (target < tc.V + 0.2 and tc.V < tc.Cruise - 1) or tc.V < 0.5
		tc.S += tc.V * dt

		-- Karosserie neigt sich beim Bremsen und in Kurven
		local acc = (tc.V - tc.LastV) / math.max(dt, 1e-3)
		tc.LastV = tc.V
		tc.Acc += (acc - tc.Acc) * math.min(1, dt * 4)
		local newPos, newDir = sampleDir(tc.Path, tc.S)
		local yawRate = dir:Cross(newDir).Y / math.max(dt, 1e-3)
		tc.Yaw = (tc.Yaw or 0) + (yawRate - (tc.Yaw or 0)) * math.min(1, dt * 4)
		local pitch = math.clamp(tc.Acc * 0.004, -0.05, 0.035)
		local roll = -math.clamp(tc.Yaw * tc.V * 0.0016, -0.05, 0.05)
		local p = newPos + Vector3.new(0, Cars.BODY_HEIGHT + 0.06, 0)
		tc.Root.CFrame = CFrame.lookAt(p, p + newDir) * A(pitch, 0, roll)
		lightOverride[tc.Car] = { Braking = tc.Braking, Blink = tc.Blink }
	end
end

-- Ampel-Lichter (alle Spieler sehen dieselbe Phase)
local LAMP = {
	Rot = { On = Color3.fromRGB(255, 40, 30), Off = Color3.fromRGB(60, 10, 10) },
	Gelb = { On = Color3.fromRGB(255, 190, 20), Off = Color3.fromRGB(60, 45, 10) },
	Gruen = { On = Color3.fromRGB(40, 255, 90), Off = Color3.fromRGB(10, 50, 20) },
}
local lastLights = 0
local updateWrenches
local function updateTrafficLights(now)
	if now - lastLights < 0.2 then
		return
	end
	lastLights = now
	for _, m in ipairs(CollectionService:GetTagged("Ampel")) do
		local state = Paths.LightState(m:GetAttribute("Axis") or "EW", now)
		local active = (state == "green" and "Gruen") or (state == "yellow" and "Gelb") or "Rot"
		for name, cols in pairs(LAMP) do
			local lamp = m:FindFirstChild(name)
			if lamp then
				lamp.Color = (name == active) and cols.On or cols.Off
			end
		end
	end
end

-- Goldene Schraubenschlüssel drehen sich; gefundene werden ausgeblendet
local wrenchBase = setmetatable({}, { __mode = "k" })
function updateWrenches(now)
	local found = "," .. (player:GetAttribute("Found") or "") .. ","
	for _, m in ipairs(CollectionService:GetTagged("Schluessel")) do
		local root = m.PrimaryPart
		if root then
			local base = wrenchBase[m]
			if not base then
				base = {}
				for _, p in ipairs(m:GetChildren()) do
					if p:IsA("BasePart") then
						base[p] = root.CFrame:ToObjectSpace(p.CFrame)
					end
				end
				base.Origin = root.CFrame
				wrenchBase[m] = base
			end
			local isFound = found:find("," .. tostring(m:GetAttribute("Id")) .. ",", 1, true) ~= nil
			local cf = base.Origin * CFrame.new(0, math.sin(now * 2) * 0.5, 0) * CFrame.Angles(0, now * 2, 0)
			for p, rel in pairs(base) do
				if typeof(p) == "Instance" then
					p.CFrame = cf * rel
					p.Transparency = isFound and 1 or 0
					local l = p:FindFirstChildOfClass("PointLight")
					if l then
						l.Enabled = not isFound
					end
				end
			end
		end
	end
end

RunService.Heartbeat:Connect(function(dt)
	local now = workspace:GetServerTimeNow()
	local cam = workspace.CurrentCamera
	local camPos = cam and cam.CFrame.Position or Vector3.zero
	local me, mine = referencePos()

	updateTraffic(dt, now, me)
	updateTrafficLights(now)
	updateWrenches(now)

	-- Räder, Lichter, Fahrer und Sound aller Autos
	for _, car in ipairs(CollectionService:GetTagged(Cars.TAG)) do
		if car:IsDescendantOf(workspace) then
			animateCar(car, dt, now, camPos, mine)
		end
	end

	-- Hat der Spieler gerade gehupt?
	local honkAt = player:GetAttribute("HonkAt")
	local honked = honkAt and (now - honkAt) < 2.5

	-- Fußgänger
	for _, w in ipairs(walkers) do
		local path = w.Way.Path
		w.Delay = w.Delay or 0
		local base = now * w.Speed + w.Phase + w.Delay
		local s, dirSign
		if path.Closed then
			s = base
			dirSign = 1
		else
			local u
			u, dirSign = pingpong(base / path.Length)
			s = u * path.Length
		end
		local pos, dir = Paths.Sample(path, s)
		dir *= dirSign
		-- Boden unter den Füßen alle 0,25 s neu messen
		w.NextGround = w.NextGround or 0
		if now >= w.NextGround or not w.GroundY then
			w.NextGround = now + 0.25 + math.random() * 0.1
			w.GroundY = groundAt(pos, w.Way.Ground)
		end
		local p = Vector3.new(pos.X, w.GroundY + w.Foot, pos.Z)
		local near = me and (me - p).Magnitude
		local close = near and near < 9 and not mine -- Spieler zu Fuß direkt daneben
		local heard = honked and near and near < 45
		if close or heard then
			-- stehen bleiben, zum Spieler schauen und winken
			w.Delay -= w.Speed * dt
			local look = Vector3.new(me.X, p.Y, me.Z)
			if (look - p).Magnitude > 0.5 then
				w.Root.CFrame = CFrame.lookAt(p, look)
			end
			if (p - camPos).Magnitude < ANIM_DISTANCE then
				playAnim(w.Person, "wave")
			end
		else
			w.Root.CFrame = CFrame.lookAt(p, p + dir)
			if (p - camPos).Magnitude < ANIM_DISTANCE then
				-- Laufanimation wie beim Spieler; Tempo passend zur Gehgeschwindigkeit
				if not playAnim(w.Person, "walk", w.Speed / 8) then
					poseWalk(w.Person, (now * w.Speed + w.Phase) * 1.15)
				end
			end
		end
	end

	-- Zuschauer
	for _, sp in ipairs(spectators) do
		if (sp.Person.PrimaryPart.Position - camPos).Magnitude < ANIM_DISTANCE then
			local kinds = { "cheer", "wave", "idle" }
			local kind = kinds[math.floor((now + sp.Seed * 3) / 5) % 3 + 1]
			if not playAnim(sp.Person, kind) then
				poseCheer(sp.Person, now, sp.Seed)
			end
		end
	end

	-- Wartende und jubelnde Kunden
	for _, person in ipairs(CollectionService:GetTagged(Npc.TAG)) do
		local pose = person:GetAttribute("Pose")
		if pose == "walk" and person.PrimaryPart and person:IsDescendantOf(workspace) then
			if not playAnim(person, "walk", 0.8) then
				poseWalk(person, now * 7)
			end
		elseif (pose == "stand" or pose == "cheer") and person.PrimaryPart and person:IsDescendantOf(workspace) then
			if (person.PrimaryPart.Position - camPos).Magnitude < ANIM_DISTANCE then
				if not playAnim(person, pose == "cheer" and "cheer" or "idle") then
					if pose == "cheer" then
						poseCheer(person, now, 1)
					else
						poseStand(person, now, (person.PrimaryPart.Position.X % 7))
					end
				end
			end
		end
	end
end)
