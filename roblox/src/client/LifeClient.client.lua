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
local function poseSit(person, steer, t, seed)
	local j = joints(person)
	setJ(j, "LeftHip", A(rad(90), 0, 0))
	setJ(j, "RightHip", A(rad(90), 0, 0))
	setJ(j, "LeftKnee", A(rad(-80), 0, 0))
	setJ(j, "RightKnee", A(rad(-80), 0, 0))
	local s = math.clamp(steer * 1.6, -0.5, 0.5)
	setJ(j, "LeftShoulder", A(rad(65) + s * 0.6, 0, rad(10)))
	setJ(j, "RightShoulder", A(rad(65) - s * 0.6, 0, rad(-10)))
	setJ(j, "LeftElbow", A(rad(25), 0, 0))
	setJ(j, "RightElbow", A(rad(25), 0, 0))
	-- Kopf: in die Kurve schauen, ab und zu umsehen
	local glance = math.sin(t * 0.7 + seed) * math.sin(t * 0.23 + seed * 2)
	setJ(j, "Neck", A(0, steer * 1.2 + glance * 0.5, 0))
	setJ(j, "Waist", A(0, 0, -steer * 0.15))
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
-- Räder und Fahrer aller Autos
------------------------------------------------------------------------
local carState = setmetatable({}, { __mode = "k" })

local function myCar()
	local char = player.Character
	local hum = char and char:FindFirstChildOfClass("Humanoid")
	local seat = hum and hum.SeatPart
	return seat and seat.Parent
end

local function animateCar(car, dt, now, camPos, mine)
	local root = car.PrimaryPart
	if not root or car == mine then
		return
	end
	local pos = root.Position
	if (pos - camPos).Magnitude > ANIM_DISTANCE then
		local st = carState[car]
		if st then
			st.LastPos = pos
			st.LastLook = root.CFrame.LookVector
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
	for _, m in ipairs(st.Motors) do
		m.Transform = A(0, m:GetAttribute("Front") and st.Steer or 0, 0) * A(st.Spin, 0, 0)
	end
	if st.Steering then
		st.Steering.Transform = A(-st.Steer * 4, 0, 0)
	end
	local driver = car:FindFirstChild("Fahrer")
	if driver then
		poseSit(driver, st.Steer, now, st.Seed)
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
				Offset = (i - 1) / n * loop.Length + li * 37,
				Speed = Config.TrafficSpeed * rng:NextNumber(0.9, 1.05),
				Delay = 0,
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
				Speed = rng:NextNumber(4.2, 6.2),
				Phase = rng:NextNumber(0, 1000),
				Foot = person:GetAttribute("FootOffset") or 2.5,
			})
		end
	end
	for _, cf in ipairs(Paths.Spectators()) do
		local person = Npc.Random(rng)
		if person then
			person.PrimaryPart.CFrame = cf * CFrame.new(0, person:GetAttribute("FootOffset") or 2.5, 0)
			person.Parent = lifeFolder
			table.insert(spectators, { Person = person, Seed = rng:NextNumber(0, 10) })
		end
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

RunService.RenderStepped:Connect(function(dt)
	local now = workspace:GetServerTimeNow()
	local cam = workspace.CurrentCamera
	local camPos = cam and cam.CFrame.Position or Vector3.zero
	local me, mine = referencePos()

	-- Verkehr bewegen
	for _, tc in ipairs(traffic) do
		local s = now * tc.Speed + tc.Offset + tc.Delay
		local pos, _ = Paths.Sample(tc.Path, s)
		local ahead = Paths.Sample(tc.Path, s + 4)
		local behind = Paths.Sample(tc.Path, s - 4)
		local dir = ahead - behind
		dir = dir.Magnitude > 0.01 and dir.Unit or Vector3.xAxis
		-- Vor dem Spieler anhalten
		if me then
			local to = me - pos
			local fwd = to:Dot(dir)
			local side = (to - dir * fwd).Magnitude
			if fwd > 0 and fwd < 20 and side < 4.5 and math.abs(to.Y) < 8 then
				tc.Delay -= tc.Speed * dt
				pos = Paths.Sample(tc.Path, now * tc.Speed + tc.Offset + tc.Delay)
			end
		end
		local p = pos + Vector3.new(0, Cars.BODY_HEIGHT + 0.06, 0)
		tc.Root.CFrame = CFrame.lookAt(p, p + dir)
	end

	-- Räder und Fahrer aller Autos
	for _, car in ipairs(CollectionService:GetTagged(Cars.TAG)) do
		if car:IsDescendantOf(workspace) then
			animateCar(car, dt, now, camPos, mine)
		end
	end

	-- Fußgänger
	for _, w in ipairs(walkers) do
		local path = w.Way.Path
		local s, dirSign
		if path.Closed then
			s = now * w.Speed + w.Phase
			dirSign = 1
		else
			local u
			u, dirSign = pingpong((now * w.Speed + w.Phase) / path.Length)
			s = u * path.Length
		end
		local pos, dir = Paths.Sample(path, s)
		dir *= dirSign
		local p = pos + Vector3.new(0, w.Way.Ground + w.Foot, 0)
		w.Root.CFrame = CFrame.lookAt(p, p + dir)
		if (p - camPos).Magnitude < ANIM_DISTANCE then
			poseWalk(w.Person, (now * w.Speed + w.Phase) * 1.15)
		end
	end

	-- Zuschauer und wartende Kunden
	for _, sp in ipairs(spectators) do
		if (sp.Person.PrimaryPart.Position - camPos).Magnitude < ANIM_DISTANCE then
			poseCheer(sp.Person, now, sp.Seed)
		end
	end
	for _, person in ipairs(CollectionService:GetTagged(Npc.TAG)) do
		if person:GetAttribute("Pose") == "stand" and person.PrimaryPart and person:IsDescendantOf(workspace) then
			if (person.PrimaryPart.Position - camPos).Magnitude < ANIM_DISTANCE then
				poseStand(person, now, (person.PrimaryPart.Position.X % 7))
			end
		end
	end
end)
