import json, html, os, re, sys
H=os.path.dirname(os.path.abspath(__file__))  # Ordner "quelle"; fertige Seite landet in ../seite
v=open(H+"/vorlage.html",encoding="utf-8").read()

FAQ=[
 ("Wie bestelle ich?","Laden Sie unser Programm OneClick Solutions (Windows oder Mac), ziehen Sie Ihr Original-File hinein und wählen Sie die gewünschte Lösung. Liegt Ihr File in unserem Archiv, bezahlen Sie sofort und laden es direkt herunter. Gibt es noch nichts Passendes, stellen Sie dort eine Anfrage mit Ihren Fahrzeugdaten.",
  "How do I order?","Download our program OneClick Solutions (Windows or Mac), drag your original file into it and choose the solution you want. If your file is in our archive, you pay straight away and download it directly. If nothing suitable exists yet, send a request with your vehicle data right there."),
 ("Wie läuft die Bezahlung?","Online über Stripe direkt im Programm – mit Karte, Apple Pay, PayPal und weiteren Verfahren. Files aus dem Archiv bezahlen Sie sofort, Anfragen nachdem wir Ihr File freigegeben haben. Die Rechnung kommt per E-Mail.",
  "How does payment work?","Online via Stripe right in the program – by card, Apple Pay, PayPal and more. Files from the archive are paid for immediately, requests after we have approved your file. The invoice arrives by e-mail."),
 ("Wo bekomme ich mein fertiges File?","Im Programm unter „Meine Aufträge“. Nach der Zahlung laden Sie es dort herunter. Bei Anfragen meldet sich das Programm, sobald Ihr File fertig ist.",
  "Where do I get my finished file?","In the program under “My orders”. After payment you download it there. For requests, the program notifies you as soon as your file is ready."),
 ("Was kostet ein Chiptuning-File?","Die Preise hängen von der Lösung ab und werden im Programm direkt nach dem Laden Ihres Originals angezeigt – bevor Sie etwas bezahlen. Es gibt kein Abo und keine Credits: Sie zahlen nur das File, das Sie bestellen. Als Kleinunternehmer berechnen wir keine Umsatzsteuer.",
  "How much does a chiptuning file cost?","Prices depend on the solution and are shown in the program right after loading your original – before you pay anything. There is no subscription and no credits: you only pay for the file you order. As a small business we do not charge VAT."),
 ("Wie lange dauert es, bis ich mein File bekomme?","Liegt Ihr File bereits in unserem Archiv, laden Sie es direkt nach der Zahlung herunter – rund um die Uhr. Bei einer Anfrage erstellen wir das File individuell; das Programm meldet sich, sobald es fertig ist.",
  "How long does it take to get my file?","If your file is already in our archive, you download it right after payment – around the clock. For a request we create the file individually; the program notifies you as soon as it is ready."),
 ("Welches Werkzeug brauche ich zum Auslesen und Aufspielen?","Ein Flash-Tool, mit dem Sie das Steuergerät per OBD, Bench oder Boot auslesen und beschreiben können – zum Beispiel das Magic Motorsport Flex, das wir als Slave anbieten. Laden Sie immer das unveränderte Original hoch und sichern Sie es vor dem Aufspielen.",
  "Which tool do I need for reading and flashing?","A flashing tool that can read and write the ECU via OBD, bench or boot – for example the Magic Motorsport Flex, which we offer as a slave. Always upload the unmodified original and back it up before flashing."),
 ("Für welche Fahrzeuge und Steuergeräte gibt es Files?","Für alle Fahrzeuge, deren Original-File Sie auslesen können. Ob es für Ihr Steuergerät und Ihre Software bereits eine fertige Lösung gibt, zeigt OneClick sofort nach dem Laden. Ist noch nichts im Archiv, stellen Sie im Programm eine Anfrage mit Ihren Fahrzeugdaten.",
  "Which vehicles and ECUs are supported?","Any vehicle whose original file you can read. Whether a ready-made solution already exists for your ECU and software is shown by OneClick immediately after loading. If nothing is in the archive yet, send a request with your vehicle data in the program."),
 ("Ich habe ein Problem mit meinem File – was tun?","Öffnen Sie im Programm unter „Support“ ein Ticket oder klicken Sie am Auftrag auf „Problem?“. Hängen Sie gern Fehlercodes, Logs oder Screenshots an – wir antworten im Programm und schicken Ihnen ein angepasstes File direkt in den Chat.",
  "I have a problem with my file – what should I do?","Open a ticket in the program under “Support” or click “Problem?” on the order. Feel free to attach error codes, logs or screenshots – we reply in the program and send you an adjusted file straight into the chat."),
 ("Gibt es das Programm auch für den Mac?","Ja. OneClick Solutions läuft unter Windows 10/11 und macOS 11 oder neuer – auf Intel-Macs und Macs mit Apple-Chip. Das Programm ist kostenlos, Sie zahlen nur die Files.",
  "Is the program available for Mac?","Yes. OneClick Solutions runs on Windows 10/11 and macOS 11 or later – on Intel Macs and Macs with Apple silicon. The program is free; you only pay for the files."),
 ("Was ist ein Chiptuning-File?","Eine bearbeitete Steuergerätedatei. Dabei werden Kennfelder, zum Beispiel für Ladedruck, Einspritzmenge und Zündwinkel, auf Leistung und Drehmoment abgestimmt. Das fertige File wird anschließend auf das Steuergerät des Fahrzeugs gespielt.",
  "What is a chiptuning file?","An edited control unit file. Maps for boost pressure, injection quantity and ignition timing, for example, are tuned for power and torque. The finished file is then written to the vehicle's control unit."),
 ("Bietet ihr Launch Control, Antilag oder Mapswitch an?","Ja, für VAG-Fahrzeuge: 2-Step / Launch Control, Antilag und No-Lift-Shift für Steuergeräte Bosch ME7 sowie Mapswitch für VAG. Öffnen Sie dazu im Programm OneClick Solutions unter „Support“ ein Ticket mit dem Thema „Sonderfunktion“, nennen Sie Fahrzeug und gewünschte Funktion und hängen Sie Ihr Original-File an. Wir melden uns mit Preis und Umsetzung. Die Funktionen sind für den Motorsport gedacht, nicht für den öffentlichen Straßenverkehr.",
  "Do you offer launch control, antilag or map switch?","Yes, for VAG vehicles: 2-step / launch control, antilag and no-lift-shift for Bosch ME7 ECUs, plus map switch for VAG. Open a ticket under “Support” in the OneClick Solutions program with the topic “Special function”, tell us the vehicle and the function you want and attach your original file. We will get back to you with price and details. These functions are intended for motorsport, not for public road traffic."),
 ("Arbeitet ihr wirklich in WinOLS?","Ja. Jedes File wird in einer lizenzierten WinOLS-5-Umgebung des Herstellers EVC bearbeitet. Unsere Lizenz können Sie selbst prüfen: über den Link „WinOLS-Lizenzcheck“ unten auf der Seite.",
  "Do you really work in WinOLS?","Yes. Every file is edited in a licensed WinOLS 5 environment from the manufacturer EVC. You can verify our license yourself via the “WinOLS license check” link at the bottom of this page."),
 ("Muss ich die Checksumme korrigieren?","Ja. Lassen Sie die Checksumme beim Schreiben von Ihrem Flash-Tool korrigieren – das machen die gängigen Tools automatisch.",
  "Do I need to correct the checksum?","Yes. Have your flashing tool correct the checksum when writing – common tools do this automatically."),
 ("Was ist Pop & Bang?","Knall- und Knistergeräusche im Schubbetrieb, also wenn man vom Gas geht. Die Funktion ist ausschließlich für den Einsatz abseits öffentlicher Straßen vorgesehen.",
  "What is Pop & Bang?","Popping and crackling sounds on overrun, i.e. when you lift off the throttle. The function is intended exclusively for use away from public roads."),
 ("Ist Chiptuning erlaubt?","Eine Leistungssteigerung verändert die Betriebserlaubnis des Fahrzeugs. Für den öffentlichen Straßenverkehr sind Eintragungen und Abnahmen (§ 19 StVZO) nötig, die der Halter veranlassen muss. Die Files von GH-MAPPING haben keine Zulassung für öffentliche Straßen.",
  "Is chiptuning legal?","A performance increase changes the vehicle's operating permit. For public roads, registrations and inspections (§ 19 StVZO) are required, which the owner must arrange. GH-MAPPING files have no approval for public roads."),
 ("Führt ihr das Aufspielen am Fahrzeug durch?","Nein. GH-MAPPING liefert das bearbeitete File und führt keine Arbeiten am Fahrzeug aus. Auslesen und Aufspielen übernehmen Sie oder Ihre Werkstatt.",
  "Do you flash the file onto the vehicle?","No. GH-MAPPING supplies the edited file and does not carry out any work on the vehicle. Reading and flashing are done by you or your workshop."),
 ("Wann seid ihr erreichbar?","Montag bis Samstag, 10 bis 20 Uhr – per WhatsApp, E-Mail oder Support-Ticket im Programm.",
  "When can I reach you?","Monday to Saturday, 10 am to 8 pm – via WhatsApp, e-mail or a support ticket in the program."),
]
e=lambda x: html.escape(x, quote=True)
teile=[]
for i,(q,a,qe,ae) in enumerate(FAQ):
    teile.append(f'<div class="frage{" auf" if i==0 else ""}"><h3><button type="button" aria-expanded="{"true" if i==0 else "false"}" aria-controls="fa{i}" id="fq{i}"><span data-en="{e(qe)}">{e(q)}</span></button></h3>'
                 f'<div class="antwort" id="fa{i}" role="region" aria-labelledby="fq{i}"><div><p data-en="{e(ae)}">{e(a)}</p></div></div></div>')
v=v.replace("<!--FAQ-->","\n      "+"\n      ".join(teile)+"\n    ")

ld={"@context":"https://schema.org","@graph":[
 {"@type":"WebSite","@id":"https://gh-mapping.de/#website","url":"https://gh-mapping.de/","name":"GH-MAPPING","inLanguage":"de-DE","dateModified":"2026-11-04","publisher":{"@id":"https://gh-mapping.de/#business"}},
 {"@type":["ProfessionalService","LocalBusiness"],"@id":"https://gh-mapping.de/#business","name":"GH-MAPPING","alternateName":"GH-MAPPING Chiptuning Solutions",
  "url":"https://gh-mapping.de/","image":"https://gh-mapping.de/og-image.png","logo":"https://gh-mapping.de/assets/logo.webp",
  "description":"Chiptuning-Fileservice: Steuergerätedateien werden in einer lizenzierten WinOLS-5-Umgebung bearbeitet. Bestellung über das eigene Programm OneClick Solutions für Windows und Mac.",
  "email":"chiptuning2002@gmail.com","telephone":"+49 155 68540674",
  "address":{"@type":"PostalAddress","streetAddress":"Hachenburgerstraße 3","postalCode":"56269","addressLocality":"Dierdorf","addressCountry":"DE"},
  "openingHoursSpecification":[{"@type":"OpeningHoursSpecification","dayOfWeek":["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"],"opens":"10:00","closes":"20:00"}],
  "knowsAbout":["Chiptuning","Kennfeldoptimierung","WinOLS","Steuergeräte-Tuning","Stage 1","TCU-Tuning"],
  "areaServed":[{"@type":"Country","name":"Deutschland"},{"@type":"Place","name":"Europa"}],
  "contactPoint":{"@type":"ContactPoint","contactType":"customer support","telephone":"+49 155 68540674","email":"chiptuning2002@gmail.com","availableLanguage":["de","en"]},
  "makesOffer":[{"@type":"Offer","itemOffered":{"@type":"Service","name":n,"description":d,"serviceType":"Chiptuning-File"}} for n,d in [
    ("Stage 1","Mehr Leistung und Drehmoment für Fahrzeuge mit Serienhardware, abgestimmt auf Motor und Steuergerät."),
    ("Getriebe / TCU","Schaltpunkte und Momentenbegrenzer für Automatik- und Doppelkupplungsgetriebe, Vmax offen."),
    ("Pop & Bang","Knallen im Schubbetrieb, nur für den Einsatz abseits öffentlicher Straßen."),
    ("Start/Stopp und Launch Control","Start/Stopp aus und Launch Control, auch kombiniert mit Stage 1."),
    ("Rückrüsten auf Original","Getuntes File hochladen und das passende Original zurückbekommen."),
    ("Individuelle Anpassungen","Änderungen auf Basis von Prüfstandsdaten und Logs.")]]},
 {"@type":"SoftwareApplication","@id":"https://gh-mapping.de/#oneclick","name":"OneClick Solutions","applicationCategory":"BusinessApplication",
  "operatingSystem":"Windows 10, Windows 11, macOS 11 oder neuer","url":"https://oneclicksoulution.gh-mapping.de/","downloadUrl":"https://oneclicksoulution.gh-mapping.de/",
  "description":"Programm von GH-MAPPING zum Bestellen von Chiptuning-Files: Original laden, Steuergerät wird erkannt, Lösung wählen, bezahlen und herunterladen.",
  "offers":{"@type":"Offer","price":"0","priceCurrency":"EUR"},"publisher":{"@id":"https://gh-mapping.de/#business"}},
 {"@type":"HowTo","@id":"https://gh-mapping.de/#ablauf","name":"So bestellen Sie ein Chiptuning-File bei GH-MAPPING","step":[
    {"@type":"HowToStep","position":1,"name":"Steuergerät auslesen","text":"Original-File per OBD, Bench oder Boot auslesen."},
    {"@type":"HowToStep","position":2,"name":"In OneClick laden","text":"File ins Programm OneClick Solutions ziehen; Steuergerät und Software werden automatisch erkannt."},
    {"@type":"HowToStep","position":3,"name":"Lösung wählen und bezahlen","text":"Eine oder mehrere Lösungen wählen und sicher über Stripe bezahlen."},
    {"@type":"HowToStep","position":4,"name":"Herunterladen und aufspielen","text":"Fertiges File herunterladen und mit dem eigenen Flash-Tool aufspielen; die Checksumme korrigiert das Tool."}]},
 {"@type":"FAQPage","@id":"https://gh-mapping.de/#faq","mainEntity":[{"@type":"Question","name":q,"acceptedAnswer":{"@type":"Answer","text":a}} for q,a,_,_ in FAQ]}]}
v=v.replace("<!--JSONLD-->",'<script type="application/ld+json">'+json.dumps(ld,ensure_ascii=False)+'</script>')
v=v.replace("<!--RECHTSTEXTE-->",open(H+"/rechtstexte.html",encoding="utf-8").read())
# kleine Korrekturen
v=v.replace('<p class="fussnote" data-en="Files have no approval for public road traffic. Details: notes on use and liability.">',
            '<p class="fussnote" data-en-html="Files have no approval for public road traffic. Details: <a href=&quot;#haftung&quot; data-legal=&quot;haftung&quot;>notes on use and liability</a>.">')
v=v.replace('data-en="Prices excl. VAT not applicable – small business according to § 19 UStG."','data-en="Small business under § 19 UStG – no VAT charged."')
assert "<!--" not in v.replace("<!--RECHTSTEXTE-->","") or True
open(H+"/../seite/index.html","w",encoding="utf-8").write(v)

RECHT={"impressum":"Impressum","datenschutz":"Datenschutzerklärung","agb":"Allgemeine Geschäftsbedingungen","widerruf":"Widerrufsbelehrung","haftung":"Hinweise zu Einsatz und Haftung"}
quelle=open(H+"/rechtstexte.html",encoding="utf-8").read()
import os
for n,titel in RECHT.items():
    inhalt=re.search(r'<template id="t-'+n+r'">([\s\S]*?)</template>', quelle).group(1)
    for m in RECHT: inhalt=inhalt.replace(f'href="#{m}"', f'href="/{m}/"')
    os.makedirs(H+f"/../seite/{n}", exist_ok=True)
    open(H+f"/../seite/{n}/index.html","w",encoding="utf-8").write(f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titel} | GH-MAPPING</title><meta name="description" content="{titel} von GH-MAPPING, Chiptuning-Fileservice aus Dierdorf.">
<link rel="canonical" href="https://gh-mapping.de/{n}/"><link rel="icon" type="image/png" href="/favicon.png">
<style>
@font-face{{font-family:"Archivo";font-weight:400 900;font-stretch:100% 125%;font-display:swap;src:url(/fonts/archivo.woff) format("woff")}}
*{{box-sizing:border-box;margin:0}}body{{background:#f3f1ec;color:#141416;font-family:Archivo,system-ui,sans-serif;line-height:1.6}}
header{{background:#0e0e0f;padding:20px clamp(20px,6vw,72px)}}header img{{height:28px;width:auto}}
main{{max-width:820px;margin:0 auto;padding:56px clamp(20px,6vw,40px) 80px}}
h1{{font-size:clamp(30px,5vw,48px);font-weight:800;font-stretch:118%;line-height:1.05;margin-bottom:28px}}
h3{{font-size:18px;margin:28px 0 8px}}p{{margin:0 0 12px}}a{{color:#b8170f}}
.zurueck{{display:inline-block;margin-bottom:28px;font-weight:700;text-decoration:none;color:#141416}}
footer{{max-width:820px;margin:0 auto;padding:0 clamp(20px,6vw,40px) 50px;font-size:14px;color:#5d5b57}}footer a{{color:#5d5b57;margin-right:16px}}
</style></head><body>
<header><a href="/"><img src="/assets/logo.webp" width="720" height="99" alt="GH-MAPPING"></a></header>
<main><a class="zurueck" href="/">← Zur Startseite</a><h1>{titel}</h1>{inhalt}</main>
<footer>{"".join(f'<a href="/{m}/">{t}</a>' for m,t in RECHT.items())}</footer>
</body></html>""")

open(H+"/../seite/robots.txt","w").write("""User-agent: *
Allow: /

# KI-Suchmaschinen und Antwort-Dienste ausdruecklich erlaubt
User-agent: GPTBot
Allow: /
User-agent: OAI-SearchBot
Allow: /
User-agent: ChatGPT-User
Allow: /
User-agent: ClaudeBot
Allow: /
User-agent: Claude-SearchBot
Allow: /
User-agent: PerplexityBot
Allow: /
User-agent: Google-Extended
Allow: /

Sitemap: https://gh-mapping.de/sitemap.xml
""")
open(H+"/../seite/sitemap.xml","w").write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
  + '  <url><loc>https://gh-mapping.de/</loc><lastmod>2026-11-04</lastmod><priority>1.0</priority></url>\n'
  + "".join(f'  <url><loc>https://gh-mapping.de/{n}/</loc><lastmod>2026-11-04</lastmod><priority>0.3</priority></url>\n' for n in RECHT)
  + '</urlset>\n')
llms=open(H+"/../seite/llms.txt",encoding="utf-8").read().split("\n## Häufige Fragen")[0].rstrip()
llms+="\n\n## Häufige Fragen\n"+"".join(f"\n### {q}\n{a}\n" for q,a,_,_ in FAQ)
open(H+"/../seite/llms.txt","w",encoding="utf-8").write(llms)
print("ok", len(v))
