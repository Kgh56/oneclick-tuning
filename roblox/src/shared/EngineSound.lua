-- Motorgeräusch eines Autos (nur auf dem Client)
-- ModuleScript "EngineSound" in ReplicatedStorage
--
-- Mischt zwei Motor-Schleifen (tief/hoch) nach Drehzahl, dazu Turbo und
-- Reifenquietschen. Die Drehzahl kommt aus einem einfachen 6-Gang-Getriebe.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Config = require(ReplicatedStorage:WaitForChild("Config"))

local EngineSound = {}
EngineSound.__index = EngineSound

EngineSound.IDLE = 900
EngineSound.REDLINE = 6900
local GEARS = { 0.2, 0.34, 0.5, 0.66, 0.83, 1.0 } -- Anteil der Höchstgeschwindigkeit je Gang

-- Drehzahl und Gang aus Geschwindigkeit (Studs/s) und Höchstgeschwindigkeit
function EngineSound.Rpm(speed, top)
	speed = math.abs(speed)
	local gear = #GEARS
	for g, r in ipairs(GEARS) do
		if speed <= top * r then
			gear = g
			break
		end
	end
	local frac = math.clamp(speed / (top * GEARS[gear]), 0, 1)
	return EngineSound.IDLE + frac * (EngineSound.REDLINE - EngineSound.IDLE), gear
end

local function makeLoop(part, key)
	local id = Config.SoundId(key)
	if not id then
		return nil
	end
	local s = Instance.new("Sound")
	s.Name = key
	s.SoundId = id
	s.Looped = true
	s.Volume = 0
	s.RollOffMode = Enum.RollOffMode.InverseTapered
	s.RollOffMinDistance = 12
	s.RollOffMaxDistance = 200
	s.Parent = part
	s:Play()
	return s
end

-- full = true: auch Turbo und Reifen (für das eigene Auto)
function EngineSound.new(part, volume, full)
	local self = setmetatable({}, EngineSound)
	self.Part = part
	self.Volume = (volume or 1) * Config.SoundVolume
	self.Low = makeLoop(part, "MotorTief")
	self.High = makeLoop(part, "MotorHoch")
	if full then
		self.Turbo = makeLoop(part, "Turbo")
		self.Tire = makeLoop(part, "Reifen")
	end
	return self
end

-- rpm: Drehzahl, load: Gas 0..1, turbo: 0..1 (Turbo-Anteil), skid: 0..1
function EngineSound:Update(rpm, load, turbo, skid)
	local v = self.Volume
	local base = (0.35 + 0.65 * load) * v
	if self.Low and self.High then
		local mix = math.clamp((rpm - 2500) / 2500, 0, 1)
		self.Low.PlaybackSpeed = rpm / 1200
		self.Low.Volume = base * (1 - mix) * 0.9 + 0.08 * v
		self.High.PlaybackSpeed = rpm / 4200
		self.High.Volume = base * mix * 0.9
	elseif self.Low then
		self.Low.PlaybackSpeed = math.min(rpm / 1200, 4)
		self.Low.Volume = base
	elseif self.High then
		self.High.PlaybackSpeed = math.max(rpm / 4200, 0.35)
		self.High.Volume = base
	end
	if self.Turbo then
		self.Turbo.PlaybackSpeed = 0.6 + rpm / 7000
		self.Turbo.Volume = (turbo or 0) * load * math.clamp((rpm - 2000) / 3000, 0, 1) * 0.3 * v
	end
	if self.Tire then
		self.Tire.Volume = (skid or 0) * 0.55 * v
		self.Tire.PlaybackSpeed = 0.9 + (skid or 0) * 0.2
	end
end

function EngineSound:Silence()
	for _, s in pairs({ self.Low, self.High, self.Turbo, self.Tire }) do
		s.Volume = 0
	end
end

function EngineSound:Destroy()
	for _, s in pairs({ self.Low, self.High, self.Turbo, self.Tire }) do
		s:Destroy()
	end
end

-- Einmaliger Sound an einem Teil (z. B. Abblasen, Fehlzündung)
function EngineSound.OneShot(part, key, volume, speed)
	local id = Config.SoundId(key)
	if not id or not part then
		return
	end
	local s = Instance.new("Sound")
	s.SoundId = id
	s.Volume = (volume or 1) * Config.SoundVolume
	s.PlaybackSpeed = speed or 1
	s.RollOffMode = Enum.RollOffMode.InverseTapered
	s.RollOffMinDistance = 12
	s.RollOffMaxDistance = 250
	s.Parent = part
	s:Play()
	task.delay(3, function()
		s:Destroy()
	end)
end

return EngineSound
