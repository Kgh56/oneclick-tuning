#!/usr/bin/env python3
"""Baut ChiptuningFirma.rbxlx aus den Skripten in src/ (ohne Rojo).

Aufruf:  python3 build_place.py
Die erzeugte Datei kann direkt in Roblox Studio geoeffnet werden.

Namensregeln wie bei Rojo:
  Name.server.lua -> Script, Name.client.lua -> LocalScript, Name.lua -> ModuleScript
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "ChiptuningFirma.rbxlx"

# Lighting.Technology: 4 = Future (beste Beleuchtung)
TECHNOLOGY_FUTURE = 4

ref = 0


def next_ref():
    global ref
    ref += 1
    return f"RBX{ref:08X}"


def cdata(text):
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def script_item(path):
    name = path.name
    if name.endswith(".server.lua"):
        cls, inst = "Script", name[: -len(".server.lua")]
    elif name.endswith(".client.lua"):
        cls, inst = "LocalScript", name[: -len(".client.lua")]
    else:
        cls, inst = "ModuleScript", name[: -len(".lua")]
    src = path.read_text(encoding="utf-8")
    return (
        f'<Item class="{cls}" referent="{next_ref()}"><Properties>'
        f'<string name="Name">{inst}</string>'
        f'<ProtectedString name="Source">{cdata(src)}</ProtectedString>'
        f"</Properties></Item>"
    )


def scripts_in(folder):
    return [script_item(p) for p in sorted((ROOT / folder).glob("*.lua"))]


def container(cls, children, props=""):
    return (
        f'<Item class="{cls}" referent="{next_ref()}"><Properties>'
        f'<string name="Name">{cls}</string>{props}</Properties>'
        + "".join(children)
        + "</Item>"
    )


xml = (
    '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">'
    + container("ReplicatedStorage", scripts_in("src/shared"))
    + container("ServerScriptService", scripts_in("src/server"))
    + container("StarterPlayer", [container("StarterPlayerScripts", scripts_in("src/client"))])
    + container("Lighting", [], f'<token name="Technology">{TECHNOLOGY_FUTURE}</token>')
    + "</roblox>\n"
)

OUT.write_text(xml, encoding="utf-8")
print(f"Geschrieben: {OUT}")
