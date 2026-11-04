#!/usr/bin/env python3
"""Baut ChiptuningFirma.rbxlx aus den Skripten in src/ (ohne Rojo).

Aufruf:  python3 build_place.py
Die erzeugte Datei kann direkt in Roblox Studio geoeffnet werden.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "ChiptuningFirma.rbxlx"

ref = 0


def next_ref():
    global ref
    ref += 1
    return f"RBX{ref:08X}"


def cdata(text):
    return "<![CDATA[" + text.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def script(cls, name, path):
    src = (ROOT / path).read_text(encoding="utf-8")
    return (
        f'<Item class="{cls}" referent="{next_ref()}"><Properties>'
        f'<string name="Name">{name}</string>'
        f'<ProtectedString name="Source">{cdata(src)}</ProtectedString>'
        f"</Properties></Item>"
    )


def container(cls, children):
    return (
        f'<Item class="{cls}" referent="{next_ref()}"><Properties>'
        f'<string name="Name">{cls}</string></Properties>'
        + "".join(children)
        + "</Item>"
    )


xml = (
    '<roblox xmlns:xmime="http://www.w3.org/2005/05/xmlmime" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:noNamespaceSchemaLocation="http://www.roblox.com/roblox.xsd" version="4">'
    + container("ReplicatedStorage", [script("ModuleScript", "Config", "src/shared/Config.lua")])
    + container("ServerScriptService", [script("Script", "GameServer", "src/server/GameServer.server.lua")])
    + container(
        "StarterPlayer",
        [container("StarterPlayerScripts", [script("LocalScript", "ChiptuningClient", "src/client/ChiptuningClient.client.lua")])],
    )
    + "</roblox>\n"
)

OUT.write_text(xml, encoding="utf-8")
print(f"Geschrieben: {OUT}")
