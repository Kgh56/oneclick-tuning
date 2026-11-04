-- Chiptuning-Firma: Fahrphysik und Tacho
-- LocalScript "DriveClient" in StarterPlayer > StarterPlayerScripts
--
-- Der Server gibt dem Fahrer die Physik des Autos (Network Owner). Hier
-- werden Gas, Bremse und Lenkung aus dem VehicleSeat gelesen und auf die
-- Constraints "Antrieb" (LinearVelocity) und "Lenkung" (AngularVelocity)
-- übertragen. Funktioniert mit Tastatur (WASD/Pfeile), Gamepad und Handy.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local player = Players.LocalPlayer
local Config = require(ReplicatedStorage:WaitForChild("Config"))
local Remotes = ReplicatedStorage:WaitForChild("Remotes")
local EndDrive = Remotes:WaitForChild("EndDrive")

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

------------------------------------------------------------------------
-- Rundenzeit auf der Teststrecke
------------------------------------------------------------------------
local T = Config.Track
local SOUTH_Z = T.CenterZ + T.Radius
local NORTH_Z = T.CenterZ - T.Radius
local lap = { Start = nil, Checkpoint = false, Best = nil, Last = nil, PrevX = nil }

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
	}
	local mass = chassis.AssemblyMass
	lv.MaxForce = math.max(8000, mass * 220)
	av.MaxTorque = math.max(40000, mass * 900)
	infoLabel.Text = ("%s · %d PS"):format(seat:GetAttribute("CarName") or "Auto", hp)
	lap.PrevX = nil
	lap.Start = nil
	lap.Checkpoint = false
	exitBtn.Text = seat:GetAttribute("Mode") == "test" and "Probefahrt beenden" or "Aussteigen"
	gui.Enabled = true
end

local function stopDriving()
	if active then
		active.LV.PlaneVelocity = Vector2.zero
		active.AV.AngularVelocity = Vector3.zero
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

	local speed = a.Speed
	if throttle > 0 then
		if speed < 0 then
			speed = math.min(0, speed + BRAKE * dt)
		else
			local falloff = 1 - 0.65 * (speed / a.Top) ^ 2
			speed = math.min(a.Top, speed + a.Accel * falloff * throttle * dt)
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

	-- Anzeige
	local kmh = math.floor(math.abs(actual) * Config.KmhFactor + 0.5)
	speedLabel.Text = tostring(kmh)
	local gearPos = (math.abs(speed) / a.Top * 5) % 1 -- Pseudo-Drehzahl mit "Gängen"
	rpmBar.Size = UDim2.fromScale(math.abs(speed) < 1 and 0.08 or 0.25 + gearPos * 0.75, 1)
	rpmBar.BackgroundColor3 = gearPos > 0.85 and Color3.fromRGB(230, 50, 50) or Color3.fromRGB(255, 140, 0)

	updateLap(chassis.Position)
	lapLabel.Text = lapText()

	local endsAt = a.Seat:GetAttribute("EndsAt")
	if endsAt then
		local left = math.max(0, endsAt - workspace:GetServerTimeNow())
		timerLabel.Text = ("🏁 Probefahrt  %d s"):format(math.ceil(left))
		timerLabel.Visible = true
	else
		timerLabel.Visible = false
	end
	unitLabel.Text = speed < -0.5 and "km/h  ·  R" or "km/h"
end)
