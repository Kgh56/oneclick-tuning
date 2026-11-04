-- Bau-Helfer für Teile, Schilder und Bewegungen
-- ModuleScript "Util" in ServerScriptService

local RunService = game:GetService("RunService")

local Util = {}

-- Erstellt ein verankertes Part. Alle Felder in props werden gesetzt.
function Util.part(props)
	local p = Instance.new("Part")
	p.Anchored = true
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	if props.Shape then
		p.Shape = props.Shape
	end
	for k, v in pairs(props) do
		if k ~= "Parent" and k ~= "Shape" then
			p[k] = v
		end
	end
	-- Flache Markierungen und Kleinteile werfen keine Schatten (läuft flüssiger)
	if props.CastShadow == nil then
		local sz = p.Size
		if math.min(sz.X, sz.Y, sz.Z) <= 0.3 or math.max(sz.X, sz.Y, sz.Z) < 1.2 then
			p.CastShadow = false
		end
	end
	p.Parent = props.Parent
	return p
end

function Util.wedge(props)
	local p = Instance.new("WedgePart")
	p.Anchored = true
	p.TopSurface = Enum.SurfaceType.Smooth
	p.BottomSurface = Enum.SurfaceType.Smooth
	for k, v in pairs(props) do
		if k ~= "Parent" then
			p[k] = v
		end
	end
	p.Parent = props.Parent
	return p
end

-- Text auf einer Fläche eines Parts
function Util.textGui(parentPart, face, text, color, bg, font)
	local sg = Instance.new("SurfaceGui")
	sg.Face = face
	sg.SizingMode = Enum.SurfaceGuiSizingMode.PixelsPerStud
	sg.PixelsPerStud = 25
	sg.LightInfluence = 0
	sg.Parent = parentPart
	local tl = Instance.new("TextLabel")
	tl.Size = UDim2.fromScale(1, 1)
	tl.BackgroundTransparency = bg and 0 or 1
	tl.BackgroundColor3 = bg or Color3.new(0, 0, 0)
	tl.Font = font or Enum.Font.GothamBlack
	tl.TextScaled = true
	tl.TextColor3 = color
	tl.Text = text
	tl.Parent = sg
	local pad = Instance.new("UIPadding")
	pad.PaddingLeft = UDim.new(0.03, 0)
	pad.PaddingRight = UDim.new(0.03, 0)
	pad.PaddingTop = UDim.new(0.08, 0)
	pad.PaddingBottom = UDim.new(0.08, 0)
	pad.Parent = tl
	return tl
end

-- Schwebendes Info-Schild
function Util.billboard(adornee, text, offsetY)
	local bb = Instance.new("BillboardGui")
	bb.Name = "Info"
	bb.Size = UDim2.fromOffset(260, 64)
	bb.StudsOffset = Vector3.new(0, offsetY or 5, 0)
	bb.AlwaysOnTop = true
	bb.MaxDistance = 90
	bb.Adornee = adornee
	local tl = Instance.new("TextLabel")
	tl.Size = UDim2.fromScale(1, 1)
	tl.BackgroundColor3 = Color3.fromRGB(20, 22, 28)
	tl.BackgroundTransparency = 0.25
	tl.TextColor3 = Color3.new(1, 1, 1)
	tl.Font = Enum.Font.GothamBold
	tl.TextScaled = true
	tl.Text = text
	tl.Parent = bb
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, 10)
	c.Parent = tl
	local pad = Instance.new("UIPadding")
	pad.PaddingLeft = UDim.new(0, 8)
	pad.PaddingRight = UDim.new(0, 8)
	pad.PaddingTop = UDim.new(0, 4)
	pad.PaddingBottom = UDim.new(0, 4)
	pad.Parent = tl
	bb.Parent = adornee
	return tl
end

function Util.light(parentPart, kind, props)
	local l = Instance.new(kind or "PointLight")
	for k, v in pairs(props or {}) do
		l[k] = v
	end
	l.Parent = parentPart
	return l
end

function Util.lookCF(pos, dir)
	return CFrame.lookAt(pos, pos + dir)
end

-- Bewegt ein Modell weich von A nach B (blockiert, bis fertig)
function Util.moveModel(model, fromCF, toCF, duration)
	local t0 = os.clock()
	while model.Parent do
		local a = math.clamp((os.clock() - t0) / duration, 0, 1)
		local e = a < 0.5 and 2 * a * a or 1 - ((-2 * a + 2) ^ 2) / 2
		local cf = fromCF:Lerp(toCF, e)
		local root = model.PrimaryPart
		if root and root.Anchored then
			root.CFrame = cf -- verschweißte Teile folgen automatisch
		else
			model:PivotTo(cf)
		end
		if a >= 1 then
			break
		end
		RunService.Heartbeat:Wait()
	end
end

-- Weicher Weg (Catmull-Rom) durch die Punkte; liefert dicht gesetzte Punkte
function Util.SmoothPath(points, perSegment)
	perSegment = perSegment or 10
	local out = {}
	local n = #points
	for i = 1, n - 1 do
		local p0 = points[math.max(i - 1, 1)]
		local p1 = points[i]
		local p2 = points[i + 1]
		local p3 = points[math.min(i + 2, n)]
		for k = 0, perSegment - 1 do
			local t = k / perSegment
			local t2, t3 = t * t, t * t * t
			local pt = (p1 * 2 + (p2 - p0) * t + (p0 * 2 - p1 * 5 + p2 * 4 - p3) * t2 + (p1 * 3 - p0 - p2 * 3 + p3) * t3) * 0.5
			table.insert(out, pt)
		end
	end
	table.insert(out, points[n])
	local cum = { 0 }
	for i = 2, #out do
		cum[i] = cum[i - 1] + (out[i] - out[i - 1]).Magnitude
	end
	return { Points = out, Cum = cum, Length = cum[#cum] }
end

local function samplePath(path, s)
	local cum, pts = path.Cum, path.Points
	s = math.clamp(s, 0, path.Length)
	local lo, hi = 1, #pts - 1
	while lo < hi do
		local mid = math.floor((lo + hi + 1) / 2)
		if cum[mid] <= s then
			lo = mid
		else
			hi = mid - 1
		end
	end
	local seg = cum[lo + 1] - cum[lo]
	local t = seg > 0 and (s - cum[lo]) / seg or 0
	return pts[lo]:Lerp(pts[lo + 1], t)
end

-- Richtung entlang des Weges (über ein Stück gemittelt, damit nichts zittert)
local function tangent(path, s)
	local a = samplePath(path, s + 1.5)
	local b = samplePath(path, s - 1.5)
	local d = a - b
	if d.Magnitude < 1e-3 then
		return nil
	end
	return d.Unit
end

-- Fährt ein Auto realistisch einen Weg ab (blockiert, bis es angekommen ist).
-- opts.Speed: Höchsttempo, opts.Reverse: rückwärts (Nase zeigt gegen die
-- Fahrtrichtung), opts.Limit(pos): optionales Tempolimit je Ort,
-- opts.StartSpeed / opts.EndSpeed: Tempo am Anfang / Ende.
function Util.DrivePath(model, points, opts)
	opts = opts or {}
	local path = Util.SmoothPath(points, 10)
	local root = model.PrimaryPart
	local maxV = opts.Speed or 15
	local accel = opts.Accel or (opts.Reverse and 4 or 7)
	local decel = opts.Decel or 9
	local endV = opts.EndSpeed or 0
	local v = opts.StartSpeed or 0
	local s = 0
	local lastLook = nil
	local blockedFor, honked = 0, false
	while s < path.Length and model.Parent do
		local dt = RunService.Heartbeat:Wait()
		-- Tempo: Kurven langsamer, rechtzeitig bremsen
		local target = maxV
		local t1 = tangent(path, s)
		local t2 = tangent(path, s + 9)
		if t1 and t2 then
			local angle = math.acos(math.clamp(t1:Dot(t2), -1, 1))
			target = math.min(target, 4 + (maxV - 4) * (1 - math.clamp(angle / 0.7, 0, 1)))
		end
		if opts.Limit then
			target = math.min(target, opts.Limit(samplePath(path, s)) or target)
		end
		local remaining = path.Length - s
		target = math.min(target, math.sqrt(endV * endV + 2 * decel * remaining))
		-- Hindernis (z. B. ein Spieler auf der Straße): anhalten und einmal hupen
		local blocked = false
		if opts.Blocked and t1 then
			-- Blickweite = halbe Autolänge + Bremsweg + Sicherheitsabstand
			local range = 9 + v * v / (2 * decel * 1.6)
			blocked = opts.Blocked(samplePath(path, s), t1, range)
		end
		if blocked then
			target = 0
			blockedFor += dt
			if blockedFor > 0.8 and not honked and opts.OnBlocked then
				honked = true
				opts.OnBlocked()
			end
		else
			blockedFor = 0
			honked = false
		end
		if v < target then
			v = math.min(target, v + accel * dt)
		else
			v = math.max(target, v - decel * 1.6 * dt)
		end
		if not blocked then
			v = math.max(v, 0.6)
		end
		s = math.min(path.Length, s + v * dt)
		local pos = samplePath(path, s)
		local tan = tangent(path, s) or lastLook
		if tan then
			local look = opts.Reverse and -tan or tan
			lastLook = tan
			root.CFrame = CFrame.lookAt(pos, pos + look)
		else
			root.CFrame = root.CFrame - root.Position + pos
		end
	end
	return v
end

return Util
