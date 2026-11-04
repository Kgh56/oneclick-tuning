-- Chiptuning-Firma: Fahrphysik und Tacho
-- LocalScript "DriveClient" in StarterPlayer > StarterPlayerScripts
--
-- Der Server gibt dem Fahrer die Physik des Autos (Network Owner). Hier
-- werden Gas, Bremse und Lenkung aus dem VehicleSeat gelesen und auf die
-- Constraints "Antrieb" (LinearVelocity) und "Lenkung" (AngularVelocity)
-- übertragen. Funktioniert mit Tastatur (WASD/Pfeile), Gamepad und Handy.

local Players = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local player = Players.LocalPlayer
local Config = require(ReplicatedStorage:WaitForChild("Config"))
local Remotes = ReplicatedStorage:WaitForChild("Remotes")
local EndDrive = Remotes:WaitForChild("EndDrive")
local EngineSound = require(ReplicatedStorage:WaitForChild("EngineSound"))
local Cars = require(ReplicatedStorage:WaitForChild("Cars"))
local Honk = Remotes:WaitForChild("Honk")
local ReportRecord = Remotes:WaitForChild("ReportRecord")
local RaceJoin = Remotes:WaitForChild("RaceJoin")
local RaceLap = Remotes:WaitForChild("RaceLap")
local RaceGrid = Remotes:WaitForChild("RaceGrid")
local CollectionService = game:GetService("CollectionService")

local BRAKE = 95
local COAST = 14
local REVERSE_MAX = 32
local REVERSE_ACCEL = 22

------------------------------------------------------------------------
-- Tacho-Anzeige
------------------------------------------------------------------------
local gui = Instance.new("ScreenGui")
gui.Name = "DriveUI"
gui.ResetOnSpawn = false
gui.Enabled = false
gui.Parent = player:WaitForChild("PlayerGui")

local function make(class, props, parent)
	local inst = Instance.new(class)
	for k, v in pairs(props) do
		inst[k] = v
	end
	inst.Parent = parent
	return inst
end

local panel = make("Frame", {
	Size = UDim2.fromOffset(300, 140),
	Position = UDim2.new(0.5, 0, 1, -16),
	AnchorPoint = Vector2.new(0.5, 1),
	BackgroundColor3 = Color3.fromRGB(18, 20, 26),
	BackgroundTransparency = 0.15,
}, gui)
make("UICorner", { CornerRadius = UDim.new(0, 14) }, panel)
make("UIStroke", { Color = Color3.fromRGB(255, 140, 0), Thickness = 2 }, panel)

local speedLabel = make("TextLabel", {
	Size = UDim2.new(1, 0, 0, 60),
	Position = UDim2.fromOffset(0, 6),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBlack,
	TextSize = 52,
	TextColor3 = Color3.new(1, 1, 1),
	Text = "0",
}, panel)
local unitLabel = make("TextLabel", {
	Size = UDim2.new(1, 0, 0, 18),
	Position = UDim2.fromOffset(0, 62),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold,
	TextSize = 15,
	TextColor3 = Color3.fromRGB(160, 165, 175),
	Text = "km/h",
}, panel)
local infoLabel = make("TextLabel", {
	Size = UDim2.new(1, -20, 0, 20),
	Position = UDim2.fromOffset(10, 84),
	BackgroundTransparency = 1,
	Font = Enum.Font.Gotham,
	TextSize = 15,
	TextColor3 = Color3.fromRGB(255, 180, 80),
	Text = "",
}, panel)
local lapLabel = make("TextLabel", {
	Size = UDim2.new(1, -20, 0, 20),
	Position = UDim2.fromOffset(10, 108),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBold,
	TextSize = 15,
	TextColor3 = Color3.fromRGB(120, 230, 140),
	Text = "",
}, panel)
-- Drehzahlbalken
local rpmBack = make("Frame", {
	Size = UDim2.new(1, -24, 0, 5),
	Position = UDim2.fromOffset(12, 4),
	BackgroundColor3 = Color3.fromRGB(50, 52, 60),
	BorderSizePixel = 0,
}, panel)
local rpmBar = make("Frame", {
	Size = UDim2.fromScale(0, 1),
	BackgroundColor3 = Color3.fromRGB(255, 140, 0),
	BorderSizePixel = 0,
}, rpmBack)

local timerLabel = make("TextLabel", {
	Size = UDim2.fromOffset(260, 44),
	Position = UDim2.new(0.5, 0, 0, 62),
	AnchorPoint = Vector2.new(0.5, 0),
	BackgroundColor3 = Color3.fromRGB(18, 20, 26),
	BackgroundTransparency = 0.2,
	Font = Enum.Font.GothamBlack,
	TextSize = 22,
	TextColor3 = Color3.new(1, 1, 1),
	Text = "",
	Visible = false,
}, gui)
make("UICorner", { CornerRadius = UDim.new(0, 10) }, timerLabel)

local exitBtn = make("TextButton", {
	Size = UDim2.fromOffset(150, 44),
	Position = UDim2.new(1, -16, 1, -16),
	AnchorPoint = Vector2.new(1, 1),
	BackgroundColor3 = Color3.fromRGB(200, 50, 50),
	Font = Enum.Font.GothamBlack,
	TextSize = 17,
	TextColor3 = Color3.new(1, 1, 1),
	Text = "Aussteigen",
}, gui)
make("UICorner", { CornerRadius = UDim.new(0, 10) }, exitBtn)
exitBtn.Activated:Connect(function()
	EndDrive:FireServer()
end)

local function smallBtn(text, y, color)
	local b = make("TextButton", {
		Size = UDim2.fromOffset(150, 40),
		Position = UDim2.new(1, -16, 1, y),
		AnchorPoint = Vector2.new(1, 1),
		BackgroundColor3 = color,
		Font = Enum.Font.GothamBlack,
		TextSize = 16,
		TextColor3 = Color3.new(1, 1, 1),
		Text = text,
	}, gui)
	make("UICorner", { CornerRadius = UDim.new(0, 10) }, b)
	return b
end
local nitroBtn = smallBtn("🔥 Nitro [N]", -66, Color3.fromRGB(40, 110, 230))
local raceBtn = smallBtn("🏁 Rennen [R]", -158, Color3.fromRGB(200, 40, 40))
local honkBtn = smallBtn("📯 Hupe [H]", -112, Color3.fromRGB(90, 90, 100))
local keysLabel = make("TextLabel", {
	Size = UDim2.fromOffset(300, 18),
	Position = UDim2.new(0.5, 0, 1, -160),
	AnchorPoint = Vector2.new(0.5, 1),
	BackgroundTransparency = 1,
	Font = Enum.Font.Gotham,
	TextSize = 13,
	TextColor3 = Color3.fromRGB(220, 220, 225),
	TextStrokeTransparency = 0.5,
	Text = "Shift halten + W im Stand = Launch Control",
}, gui)
keysLabel.Visible = UserInputService.KeyboardEnabled
local nitroBar = make("Frame", {
	Size = UDim2.new(1, -24, 0, 4),
	Position = UDim2.new(0, 12, 1, -6),
	BackgroundColor3 = Color3.fromRGB(40, 110, 230),
	BorderSizePixel = 0,
}, panel)

------------------------------------------------------------------------
-- Rundenzeit auf der Teststrecke
------------------------------------------------------------------------
local T = Config.Track
local SOUTH_Z = T.CenterZ + T.Radius
local NORTH_Z = T.CenterZ - T.Radius
local lap = { Start = nil, Checkpoint = false, Best = nil, Last = nil, PrevX = nil }
local raceLaps = 0

local function fmtTime(t)
	local m = math.floor(t / 60)
	local s = t - m * 60
	return ("%d:%05.2f"):format(m, s)
end

local function updateLap(pos)
	local prevX = lap.PrevX
	lap.PrevX = pos.X
	if not prevX then
		return
	end
	local onSouth = math.abs(pos.Z - SOUTH_Z) < T.Width / 2 + 4
	local onNorth = math.abs(pos.Z - NORTH_Z) < T.Width / 2 + 4
	-- Start/Ziel: Süd-Gerade bei x = 0, Fahrtrichtung +X
	if onSouth and prevX < 0 and pos.X >= 0 then
		local now = os.clock()
		if lap.Start and lap.Checkpoint then
			lap.Last = now - lap.Start
			ReportRecord:FireServer("lap", lap.Last)
			if player:GetAttribute("Racing") and ReplicatedStorage:GetAttribute("RacePhase") == "running" then
				raceLaps += 1
				RaceLap:FireServer(raceLaps)
			end
			if not lap.Best or lap.Last < lap.Best then
				lap.Best = lap.Last
			end
		end
		lap.Start = now
		lap.Checkpoint = false
	elseif onNorth and prevX > 0 and pos.X <= 0 then
		lap.Checkpoint = true
	end
end

local function lapText()
	local parts = {}
	if lap.Start then
		table.insert(parts, "Runde " .. fmtTime(os.clock() - lap.Start))
	end
	if lap.Best then
		table.insert(parts, "Beste " .. fmtTime(lap.Best))
	end
	return table.concat(parts, "   ")
end

------------------------------------------------------------------------
-- Stunts: Sprünge, Kicker, Slalom, Blitzer
------------------------------------------------------------------------
local stuntLabel = make("TextLabel", {
	Size = UDim2.fromOffset(520, 60),
	Position = UDim2.new(0.5, 0, 0, 120),
	AnchorPoint = Vector2.new(0.5, 0),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBlack,
	TextSize = 34,
	TextColor3 = Color3.fromRGB(255, 200, 40),
	TextStrokeTransparency = 0.2,
	Text = "",
}, gui)
local stuntToken = 0
local function showStunt(text, color)
	stuntToken += 1
	local token = stuntToken
	stuntLabel.Text = text
	stuntLabel.TextColor3 = color or Color3.fromRGB(255, 200, 40)
	task.delay(2.5, function()
		if stuntToken == token then
			stuntLabel.Text = ""
		end
	end)
end

local stunt = { Air = false, AirStart = 0, AirPos = nil, KickerAt = 0, Slalom = nil, BlitzAt = 0 }
local rayParams = RaycastParams.new()
rayParams.FilterType = Enum.RaycastFilterType.Exclude

local function nearTagged(tag, pos)
	for _, p in ipairs(CollectionService:GetTagged(tag)) do
		local rel = p.CFrame:PointToObjectSpace(pos)
		local half = p.Size / 2
		if math.abs(rel.X) <= half.X and math.abs(rel.Y) <= half.Y + 2 and math.abs(rel.Z) <= half.Z then
			return p
		end
	end
	return nil
end

local exhaustFlame -- weiter unten definiert

local function updateStunts(a, _dt, speed)
	local chassis = a.Chassis
	local pos = chassis.Position
	local clock = os.clock()

	-- Kicker an der Schanzenkante: Schub nach oben
	if clock - stunt.KickerAt > 1 and speed > 25 then
		local k = nearTagged("Kicker", pos)
		if k then
			stunt.KickerAt = clock
			local v = chassis.AssemblyLinearVelocity
			chassis.AssemblyLinearVelocity = Vector3.new(v.X, math.max(v.Y, 0) + (k:GetAttribute("Boost") or 50) * math.clamp(speed / 90, 0.5, 1.3), v.Z)
			EngineSound.OneShot(chassis, "Abblasen", 0.7, 0.8)
		end
	end

	-- Flugphase messen
	local ignore = { a.Seat.Parent }
	if player.Character then
		table.insert(ignore, player.Character)
	end
	rayParams.FilterDescendantsInstances = ignore
	local hit = workspace:Raycast(pos, Vector3.new(0, -3.2, 0), rayParams)
	if not hit and not stunt.Air then
		stunt.Air = true
		stunt.AirStart = clock
		stunt.AirPos = pos
	elseif hit and stunt.Air then
		stunt.Air = false
		local air = clock - stunt.AirStart
		if air > 0.45 and stunt.AirPos then
			local dist = (Vector3.new(pos.X, 0, pos.Z) - Vector3.new(stunt.AirPos.X, 0, stunt.AirPos.Z)).Magnitude * 0.28
			showStunt(("✈️ %.1f s Flug · %d m"):format(air, math.floor(dist + 0.5)))
			if dist > 25 then
				EngineSound.UI("Jubel", 0.4)
			end
			if dist >= 3 then
				ReportRecord:FireServer("jump", dist)
			end
		end
	end

	-- Slalom: Start- und Zieltor, Strafe für berührte Pylonen
	if nearTagged("SlalomStart", pos) and (not stunt.Slalom or clock - stunt.Slalom.Start > 3) then
		stunt.Slalom = { Start = clock, Penalty = 0, Hit = {} }
		showStunt("🏁 Slalom gestartet!", Color3.fromRGB(120, 230, 140))
	elseif stunt.Slalom then
		for _, cone in ipairs(CollectionService:GetTagged("Pylone")) do
			if not stunt.Slalom.Hit[cone] and (Vector3.new(cone.Position.X, pos.Y, cone.Position.Z) - pos).Magnitude < 3.2 then
				stunt.Slalom.Hit[cone] = true
				stunt.Slalom.Penalty += 1
				showStunt("⚠️ Pylone! +1 s", Color3.fromRGB(255, 120, 60))
			end
		end
		if nearTagged("SlalomZiel", pos) and clock - stunt.Slalom.Start > 3 then
			local t = clock - stunt.Slalom.Start + stunt.Slalom.Penalty
			showStunt(("🏁 Slalom: %.2f s"):format(t), Color3.fromRGB(120, 230, 140))
			ReportRecord:FireServer("slalom", t)
			stunt.Slalom = nil
		elseif clock - stunt.Slalom.Start > 90 then
			stunt.Slalom = nil
		end
	end

	-- Boost-Felder
	local pad = nearTagged("Boostfeld", pos)
	if pad and clock > (a.PadUntil or 0) - 1 then
		local padDir = pad.CFrame.LookVector
		if chassis.CFrame.LookVector:Dot(padDir) > 0.5 then
			if clock > (a.PadUntil or 0) then
				EngineSound.OneShot(chassis, "Abblasen", 0.8, 0.7)
				showStunt("⚡ BOOST!", Color3.fromRGB(80, 200, 255))
				exhaustFlame(a, true, 1.2)
			end
			a.PadUntil = clock + 1.6
			a.Speed = math.max(a.Speed, math.min(a.Top * Config.NitroBoost, a.Speed + 30))
		end
	end

	-- Blitzer
	if clock - stunt.BlitzAt > 3 then
		for _, cam in ipairs(CollectionService:GetTagged("Blitzer")) do
			local rel = pos - cam.Position
			if math.abs(rel.X) < 8 and math.abs(rel.Z) < 30 and math.abs(rel.Y) < 20 or (math.abs(rel.Z) < 8 and math.abs(rel.X) < 30 and math.abs(rel.Y) < 20) then
				local kmh = math.floor(math.abs(speed) * Config.KmhFactor + 0.5)
				if kmh > 30 then
					stunt.BlitzAt = clock
					local light = cam:FindFirstChildOfClass("PointLight")
					if light then
						light.Brightness = 12
						task.delay(0.15, function()
							light.Brightness = 0
						end)
					end
					showStunt(("📸 Geblitzt: %d km/h"):format(kmh), Color3.fromRGB(255, 255, 255))
					EngineSound.OneShot(cam, "Blitzer", 0.9)
					ReportRecord:FireServer("speed", kmh)
				end
			end
		end
	end
end

------------------------------------------------------------------------
-- Fahrlogik
------------------------------------------------------------------------
local active = nil

local function startDriving(seat)
	local car = seat.Parent
	local chassis = car and car.PrimaryPart
	local lv = chassis and chassis:FindFirstChild("Antrieb")
	local av = chassis and chassis:FindFirstChild("Lenkung")
	if not (lv and av) then
		return
	end
	local hp = seat:GetAttribute("Hp") or 150
	local stats = Config.DriveStats(hp)
	local wheelMotors = {}
	for _, m in ipairs(chassis:GetChildren()) do
		if m:IsA("Motor6D") and m.Name:sub(1, 3) == "Rad" then
			table.insert(wheelMotors, m)
		end
	end
	active = {
		WheelMotors = wheelMotors,
		SteeringWheel = chassis:FindFirstChild("LenkradMotor"),
		Spin = 0,
		SteerVis = 0,
		Seat = seat,
		Chassis = chassis,
		LV = lv,
		AV = av,
		Speed = 0,
		Top = stats.TopSpeed,
		Accel = stats.Accel,
		Hp = hp,
		Rpm = EngineSound.IDLE,
		Gear = 1,
		LastThrottle = 0,
		TurboAmt = hp >= 150 and 1 or 0.35,
		Sound = EngineSound.new(chassis, 1, true),
		Exhausts = {},
		Lights = Cars.LightParts(car),
		PopBang = seat:GetAttribute("PopBang") == true,
		NitroUntil = 0,
		NitroReady = 0,
		LaunchBoostUntil = 0,
		Launching = false,
	}
	local mass = chassis.AssemblyMass
	lv.MaxForce = math.max(8000, mass * 220)
	av.MaxTorque = math.max(40000, mass * 900)
	infoLabel.Text = ("%s · %d PS"):format(seat:GetAttribute("CarName") or "Auto", hp)
	lap.PrevX = nil
	lap.Start = nil
	lap.Checkpoint = false
	exitBtn.Text = seat:GetAttribute("Mode") == "test" and "Probefahrt beenden" or "Aussteigen"
	for _, d in ipairs(car:GetDescendants()) do
		if d.Name == "Auspuff" and d:IsA("BasePart") then
			table.insert(active.Exhausts, d)
		end
	end
	gui.Enabled = true
end

-- Flammen aus dem Auspuff (nur optisch, lokal)
exhaustFlame = function(a, blue, duration)
	for _, ex in ipairs(a.Exhausts) do
		local f = Instance.new("Fire")
		f.Size = blue and 3.5 or 2.5
		f.Heat = blue and 6 or 2
		f.Color = blue and Color3.fromRGB(60, 120, 255) or Color3.fromRGB(255, 120, 30)
		f.SecondaryColor = blue and Color3.fromRGB(180, 220, 255) or Color3.fromRGB(255, 230, 120)
		f.Parent = ex
		task.delay(duration or 0.25, function()
			f.Enabled = false
			task.delay(1, function()
				f:Destroy()
			end)
		end)
	end
end

-- Pop & Bang: mehrere Knaller mit Flammen beim Gaswegnehmen
local function crackle(a, count)
	task.spawn(function()
		for _ = 1, count do
			if active ~= a then
				return
			end
			EngineSound.OneShot(a.Chassis, "Fehlzuendung", 0.55, 0.85 + math.random() * 0.5)
			exhaustFlame(a, false, 0.08)
			task.wait(0.08 + math.random() * 0.17)
		end
	end)
end

local function nitro()
	local a = active
	if not a then
		return
	end
	local now = os.clock()
	if now < a.NitroReady then
		return
	end
	a.NitroUntil = now + Config.NitroSeconds
	a.NitroReady = now + Config.NitroSeconds + Config.NitroCooldown
	exhaustFlame(a, true, Config.NitroSeconds)
	EngineSound.OneShot(a.Chassis, "Abblasen", 0.9, 0.6)
end

local lastHonk = 0
local function honk()
	if active and os.clock() - lastHonk > 0.6 then
		lastHonk = os.clock()
		Honk:FireServer()
	end
end

nitroBtn.Activated:Connect(nitro)
honkBtn.Activated:Connect(honk)
UserInputService.InputBegan:Connect(function(input, processed)
	if processed or not active then
		return
	end
	if input.KeyCode == Enum.KeyCode.N or input.KeyCode == Enum.KeyCode.ButtonY then
		nitro()
	elseif input.KeyCode == Enum.KeyCode.R then
		RaceJoin:FireServer()
	elseif input.KeyCode == Enum.KeyCode.H or input.KeyCode == Enum.KeyCode.ButtonX then
		honk()
	end
end)

------------------------------------------------------------------------
-- Rennen: Startplatz, Startampel, Runden
------------------------------------------------------------------------
raceBtn.Activated:Connect(function()
	RaceJoin:FireServer()
end)

RaceGrid.OnClientEvent:Connect(function(cf)
	local a = active
	if not a then
		return
	end
	a.Chassis.AssemblyLinearVelocity = Vector3.zero
	a.Chassis.CFrame = cf + Vector3.new(0, 0.5, 0)
	a.Speed = 0
	raceLaps = 0
	lap.Start = nil
	lap.Checkpoint = false
	lap.PrevX = nil
end)

local raceLabel = make("TextLabel", {
	Size = UDim2.fromOffset(400, 120),
	Position = UDim2.new(0.5, 0, 0.3, 0),
	AnchorPoint = Vector2.new(0.5, 0.5),
	BackgroundTransparency = 1,
	Font = Enum.Font.GothamBlack,
	TextSize = 90,
	TextColor3 = Color3.fromRGB(255, 60, 60),
	TextStrokeTransparency = 0.1,
	Text = "",
}, gui)
local lastCount = nil
RunService.RenderStepped:Connect(function()
	local phase = ReplicatedStorage:GetAttribute("RacePhase")
	local racing = player:GetAttribute("Racing")
	raceBtn.Text = racing and ((phase == "lobby") and "🏁 Warte auf Start" or ("🏁 Runde %d/%d"):format(math.min(raceLaps + 1, ReplicatedStorage:GetAttribute("RaceLaps") or 2), ReplicatedStorage:GetAttribute("RaceLaps") or 2)) or (phase == "lobby" and "🏁 Mitmachen! [R]" or "🏁 Rennen [R]")
	if racing and phase == "countdown" then
		local left = (ReplicatedStorage:GetAttribute("RaceStartAt") or 0) - workspace:GetServerTimeNow()
		local n = math.ceil(left)
		if n ~= lastCount and n >= 1 and n <= 3 then
			EngineSound.UI("PiepKurz", 0.7)
		end
		lastCount = n
		raceLabel.Text = (n >= 1 and n <= 3) and tostring(n) or ""
		raceLabel.TextColor3 = Color3.fromRGB(255, 60, 60)
	elseif racing and phase == "running" and lastCount ~= nil and lastCount >= 1 then
		lastCount = 0
		EngineSound.UI("PiepLang", 0.8)
		raceLabel.Text = "GO!"
		raceLabel.TextColor3 = Color3.fromRGB(80, 255, 120)
		task.delay(1.2, function()
			raceLabel.Text = ""
		end)
	elseif not racing then
		lastCount = nil
		if raceLabel.Text ~= "" and raceLabel.Text ~= "GO!" then
			raceLabel.Text = ""
		end
	end
end)

local function stopDriving()
	if active then
		active.LV.PlaneVelocity = Vector2.zero
		active.AV.AngularVelocity = Vector3.zero
		active.Sound:Destroy()
		Cars.SetLights(active.Lights, false, 0, 0)
	end
	active = nil
	gui.Enabled = false
end

local function getHumanoid()
	local char = player.Character
	return char and char:FindFirstChildOfClass("Humanoid")
end

RunService.Heartbeat:Connect(function(dt)
	-- Sitzt der Spieler in einem fahrbaren Auto?
	local hum = getHumanoid()
	local seat = hum and hum.SeatPart
	if seat and seat:IsA("VehicleSeat") and seat:GetAttribute("Drivable") and seat:GetAttribute("Owner") == player.UserId then
		if not active or active.Seat ~= seat then
			startDriving(seat)
		end
	elseif active then
		stopDriving()
	end
	if not active then
		return
	end
	if not active.Chassis.Parent then
		stopDriving()
		return
	end

	local a = active
	local chassis = a.Chassis
	local throttle = a.Seat.ThrottleFloat
	local steer = a.Seat.SteerFloat

	local look = chassis.CFrame.LookVector
	local dir = Vector3.new(look.X, 0, look.Z)
	if dir.Magnitude < 0.05 then
		return
	end
	dir = dir.Unit
	local actual = chassis.AssemblyLinearVelocity:Dot(dir)

	local clock = os.clock()
	local nitroOn = clock < a.NitroUntil
	local padOn = clock < (a.PadUntil or 0)
	local top = (nitroOn or padOn) and a.Top * Config.NitroBoost or a.Top
	local accel = a.Accel
	if nitroOn or padOn then
		accel *= 2
	end
	-- Rennen: vor dem Start festhalten
	local raceHold = player:GetAttribute("Racing") and ReplicatedStorage:GetAttribute("RacePhase") == "countdown"
	if clock < a.LaunchBoostUntil then
		accel *= 1.8
	end
	-- Launch Control: Shift halten im Stand, Drehzahl wird gehalten
	local shift = UserInputService:IsKeyDown(Enum.KeyCode.LeftShift)
	local wasLaunching = a.Launching
	a.Launching = shift and throttle > 0 and math.abs(a.Speed) < 3
	if wasLaunching and not a.Launching and throttle > 0 then
		a.LaunchBoostUntil = clock + 1.6
		exhaustFlame(a, false, 0.3)
	end

	local speed = a.Speed
	if a.Launching or raceHold then
		speed = 0
	elseif throttle > 0 then
		if speed < 0 then
			speed = math.min(0, speed + BRAKE * dt)
		else
			local falloff = 1 - 0.65 * math.min(1, speed / top) ^ 2
			speed = math.min(top, speed + accel * falloff * throttle * dt)
		end
	elseif throttle < 0 then
		if speed > 0 then
			speed = math.max(0, speed - BRAKE * dt)
		else
			speed = math.max(-REVERSE_MAX, speed - REVERSE_ACCEL * dt)
		end
	else
		local drop = math.min(math.abs(speed), COAST * dt)
		speed -= drop * math.sign(speed)
	end
	-- Aufprall: plötzlich viel langsamer -> Krach
	if a.Speed - actual > 28 and a.Speed > 30 and clock - (a.CrashAt or 0) > 1 then
		a.CrashAt = clock
		EngineSound.OneShot(chassis, "Aufprall", math.clamp((a.Speed - actual) / 60, 0.4, 1))
	end
	-- Gegen eine Wand gefahren: Geschwindigkeit an die echte anpassen
	if speed > 0 and speed > actual + 10 then
		speed = math.max(0, actual + 10)
	elseif speed < 0 and speed < actual - 10 then
		speed = math.min(0, actual - 10)
	end
	a.Speed = speed

	local v = dir * speed
	a.LV.PlaneVelocity = Vector2.new(v.X, v.Z)

	local grip = math.clamp(math.abs(speed) / 20, 0, 1)
	local maxYaw = 2.1 - 1.0 * math.clamp(math.abs(speed) / a.Top, 0, 1)
	local yaw = -steer * maxYaw * grip * (speed >= 0 and 1 or -1)
	a.AV.AngularVelocity = Vector3.new(0, yaw, 0)

	-- Räder drehen und Vorderräder lenken (Radius 1.2 Studs)
	a.Spin = (a.Spin - actual / 1.2 * dt) % (math.pi * 2)
	a.SteerVis += (steer - a.SteerVis) * math.min(1, dt * 10)
	local steerAngle = -a.SteerVis * 0.55
	for _, motor in ipairs(a.WheelMotors) do
		local wheelYaw = motor:GetAttribute("Front") and steerAngle or 0
		motor.Transform = CFrame.Angles(0, wheelYaw, 0) * CFrame.Angles(a.Spin, 0, 0)
	end
	if a.SteeringWheel then
		a.SteeringWheel.Transform = CFrame.Angles(a.SteerVis * 2.2, 0, 0)
	end

	-- Motor: Drehzahl aus dem Getriebe, Sounds
	local targetRpm, gear = EngineSound.Rpm(speed, a.Top)
	if throttle ~= 0 then
		targetRpm = math.max(targetRpm, 1700) -- Kupplung beim Anfahren
	end
	if a.Launching then
		targetRpm = Config.LaunchRpm + math.sin(clock * 30) * 150 -- Begrenzer
		if math.random() < dt * 3 then
			crackle(a, 1)
		end
	end
	a.Rpm += (targetRpm - a.Rpm) * math.min(1, dt * 10)
	if gear > a.Gear and throttle > 0 then
		EngineSound.OneShot(chassis, "Abblasen", 0.45 * a.TurboAmt)
	end
	a.Gear = gear
	if a.LastThrottle > 0 and throttle <= 0 and a.Rpm > (a.PopBang and 3000 or 4300) then
		EngineSound.OneShot(chassis, "Abblasen", 0.6 * a.TurboAmt)
		if a.PopBang then
			crackle(a, math.random(4, 7))
		elseif a.Hp >= 300 then
			EngineSound.OneShot(chassis, "Fehlzuendung", 0.8)
			exhaustFlame(a)
		end
	end
	-- Schiebebetrieb mit Pop & Bang: ab und zu ein Knall
	if a.PopBang and throttle <= 0 and a.Rpm > 2500 and math.random() < dt * 2.5 then
		crackle(a, 1)
	end
	Cars.SetLights(a.Lights, throttle < 0 and speed > 1, 0, clock)
	nitroBar.Size = UDim2.new(math.clamp(1 - (a.NitroReady - clock) / (Config.NitroSeconds + Config.NitroCooldown), 0, 1), -24, 0, 4)
	nitroBtn.Text = (clock >= a.NitroReady) and "🔥 Nitro [N]" or (nitroOn and "🔥 NITRO!" or ("⏳ %d s"):format(math.ceil(a.NitroReady - clock)))
	a.LastThrottle = throttle
	local skid = math.clamp(math.abs(steer) * (math.abs(speed) - 45) / 60, 0, 1)
	if throttle < 0 and speed > 35 then
		skid = math.max(skid, 0.5)
	end
	a.Sound:Update(a.Rpm, math.abs(throttle), nitroOn and 1.6 or a.TurboAmt, skid)

	-- Anzeige
	local kmh = math.floor(math.abs(actual) * Config.KmhFactor + 0.5)
	speedLabel.Text = tostring(kmh)
	local rpmFrac = a.Rpm / 7000
	rpmBar.Size = UDim2.fromScale(math.clamp(rpmFrac, 0.05, 1), 1)
	rpmBar.BackgroundColor3 = a.Rpm > 6200 and Color3.fromRGB(230, 50, 50) or Color3.fromRGB(255, 140, 0)

	updateLap(chassis.Position)
	updateStunts(a, dt, speed)
	lapLabel.Text = lapText()

	local endsAt = a.Seat:GetAttribute("EndsAt")
	if endsAt then
		local left = math.max(0, endsAt - workspace:GetServerTimeNow())
		timerLabel.Text = ("🏁 Probefahrt  %d s"):format(math.ceil(left))
		timerLabel.Visible = true
	else
		timerLabel.Visible = false
	end
	unitLabel.Text = speed < -0.5 and "km/h  ·  R" or ("km/h  ·  %d. Gang  ·  %d U/min"):format(a.Gear, math.floor(a.Rpm / 100) * 100)
end)
