# Plán implementace: detailní hudební mapa a piano roll

**Projekt:** StarDance SongSheet Studio  
**Stav:** Základní piano roll, MIDI workflow, vratná editace not a značek a lokální desktopový engine jsou implementovány; testovací web je Site v11 a desktopové vydání je v0.3.0. Zbývá pilot na skutečných skladbách a kontrola na cílovém hardwaru.  
**Aktualizováno:** 11. 11. 2026

## 1. Cíl

Rozšířit editor tak, aby uměl lokálně analyzovat celou skladbu a ukázal její odhadnuté noty po jednotlivých nástrojích v editovatelném gridu podobném piano rollu v Abletonu. Nad ním zůstane waveform, společný playhead a časování pro práci světelného designéra. Samostatná časová mapa aktivity ukáže, kdy je který nástroj slyšet nebo kdy podle přepisu hraje.

Značky odvozené z analýzy budou návrhy k poslechu a úpravě. Značka ani výsledek modelu se sám od sebe nestane potvrzeným GO cue.

### Stav k 11. 11. 2026

| Část | Stav | Ověření / omezení |
| --- | --- | --- |
| Lokální MuScriptor C++ adaptér | Implementován; Linuxový wrapper sestaven | Chybové rozhraní ověřeno. Bez skutečného audia a vah nelze v tomto běhu vyhodnotit kvalitu přepisu ani rychlost. |
| MIDI a projektová data | Hotovo v desktopové i webové verzi | Formát 0/1, editace, export, zachování checkpointu při uložení projektu. |
| Piano roll a notová aktivita | Hotovo v obou klientech | Přímé tažení i tabulka; filtr vybrané stopy a kandidátní cue podle filtru. Undo/redo not a značek i export mapy do PNG fungují v desktopu i webu. |
| LD návrhy | Implementováno | Nástup a hustota not vytvářejí upravitelné návrhy, které vyžadují poslechovou kontrolu. |
| Licence vah | Výslovně potvrzen nekomerční pilot | Uživatel upřesnil, že veškeré použití modelových vah v pilotu bude nekomerční. Aplikace zobrazí upozornění CC BY-NC 4.0 před prvním stažením. |
| Windows/macOS balíčky a hardware | Čeká | Sestavení a test musí proběhnout na těchto OS; aktuální workspace je Linux. |
| Webová stránka Sites | Nasazeno jako verze 11 | Zachován LD cuebook, jeho podklady i předání do editoru; URL zůstala stejná. Přidané undo/redo a export hudební mapy do PNG. Statická kontrola skriptů prošla; vizuální kontrola v prohlížeči v tomto workspace nebyla dostupná. |
| GitHub vydání | v0.3.0 | Zdrojové změny, dokumentace a Windows/macOS balíčky jsou publikovány v [GitHub Releases](https://github.com/lightingcze/StarDance_SongSheet_Studio/releases/tag/v0.3.0). |
| Pilot na skutečných skladbách | Čeká na audio | V připojené složce „Nahrávky kapely čtvrtek“ jsou nahrávky pouze pro díly 1–5. Pro rozsah 6+ je potřeba produkční WAV nebo vhodný audio výřez; nutný poslechový audit nástrojů, not a časování. |

## 2. Doporučený směr

- **Model k ověření:** MuScriptor, nejlépe nejprve přes NeuralNote 2.2 jako referenční nástroj a poté přes lokální C++ inference engine `muscriptor.cpp`. MuScriptor převádí celý mix na notové události s nástupem, koncem, výškou tónu a nástrojem; inference lze spustit lokálně a po částech.
- **První volba pro editor:** lokální nativní engine, který vrací strojově čitelný seznam not. `muscriptor.cpp` je určen pro CPU/Metal/Vulkan a nevyžaduje Python za běhu; aktuální upstream ověřuje macOS Apple Silicon a Windows, Intel Mac je zatím méně ověřený. [Projekt `muscriptor.cpp`](https://github.com/DamRsn/muscriptor.cpp)
- **Současné nástrojové skóre:** ponechat YAMNet/AudioSet jako samostatnou aktivitu zvukových tříd. Nenahrazuje notový přepis ani izolované stopy. Webový SCNet zůstane volitelným rozdělením na čtyři hrubé vrstvy.
- **Licence testovacího modelu:** uživatel výslovně potvrdil, že veškeré použití vah MuScriptoru v tomto pilotu bude nekomerční. Zdrojový kód a balíčky v0.3.0 jsou veřejně publikované bez vah; aplikace je nestahuje do instalátoru a před samostatným stažením zobrazuje licenční upozornění. Před komerčním použitím vah nebo jejich přibalením k aplikaci znovu prověřit licenci. [Licence a lokální běh MuScriptoru](https://github.com/muscriptor/muscriptor)

MuScriptor je vhodnější než samotný klasifikátor nástrojů pro zobrazení ve stylu Abletonu: kromě štítku nástroje vytváří časované notové události. NeuralNote už tuto kombinaci zobrazuje jako seznam nástrojů, waveform a barevné noty v piano rollu a běží lokálně na Windows i macOS. [NeuralNote](https://neuralnote.co/)

## 3. Co už projekt umí

- Desktopová aplikace má přehrávání, waveform, playhead a ručně editovatelné značky v časování 25 fps. [Přehled funkcí](README.md)
- Desktop už ukládá časová skóre nástrojových tříd YAMNet/AudioSet po 0,48 s a kandidátní události; rozhraní pro analýzu běží na pracovním vlákně. [Stavový model a analýza YAMNet](app.py)
- Webová verze má stejný základ přehrávání a značek, časovou aktivitu a navíc browserové SCNet rozdělení na vokál, bicí, basu a ostatní. [Webové audio pracovní prostředí](web/index.html)
- Soubor projektu je nyní verze 2 a volitelně ukládá `music_analysis`; starší projekty dostávají prázdnou notovou mapu bez změny existujících polí.

Hlavní mezera: současný graf ukazuje skóre tříd nebo hrubé události, ne konkrétní noty s výškou, délkou a instrumentem v samostatných stopách.

## 4. Zamýšlené pracovní prostředí

### Zobrazení

1. **Horní pás:** waveform nahrávky, společný playhead, čas v `HH:MM:SS:FF`, značky, takty a doby.
2. **Piano roll:** vodorovně čas, svisle výška MIDI noty. Každý detekovaný nástroj má vlastní barevnou stopu a noty jsou bloky s editovatelným začátkem, koncem a výškou.
3. **Aktivita nástrojů:** sbalitelný přehled po jednotlivých stopách. Ukáže aktivní noty, jejich hustotu a změny v čase. Tento pruh bude označen jako odvozená aktivita, nikoli jako naměřená hlasitost nebo kalibrovaná pravděpodobnost.
4. **Panel stop:** zobrazit/skrýt, sólo, mute, přejmenovat a filtrovat nástroje; přehrát rozpoznané noty syntézou a porovnat je s původním mixem.
5. **Časová osa světel:** zachovat tabulku a ruční značky. Z notových událostí bude možné připravit kandidáty při nástupu nástroje, změně hustoty, výplni nebo výrazném přechodu.

Grid může používat taktovou mřížku jako vodítko, ale výchozí zobrazení nesmí automaticky přepis přichytit k době. Modelové časy not uchovat přesněji než 25 fps; na nejbližší snímek zaokrouhlovat až světelné značky a tiskové časové kódy. Případné přichycení not k době bude samostatná vratná volba.

### Interakce

- Kliknutí na notu nebo pruh aktivity posune přehrávání na odpovídající čas.
- Tažením lze notu přesunout nebo změnit její délku; změna výšky noty a přesná editace v tabulce budou dostupné jako alternativy.
- Ručně přidané, změněné a smazané noty budou označené jako uživatelská úprava, odděleně od výsledku AI.
- Filtr podle nástroje ovlivní piano roll, aktivitu i generování kandidátních značek.
- Při generování značek se vždy zobrazí důvod, např. „nástup smyčců“ nebo „hustý bicí fill“, a původ z modelu. Uživatel rozhodne, co ponechat.

## 5. Plán etap a kontrolní body

### Etapa A — ověření modelu a licenčního režimu

- Použít NeuralNote 2.2 jako hotovou referenci pro piano roll a porovnat jeho výstup se stejnými skladbami, které budou použity pro interní test.
- Na několika reprezentativních celých skladbách porovnat dostupné velikosti modelu. Nevybírat „největší“ automaticky: ověřit, zda lepší detail odpovídá době zpracování a hardwaru.
- Zapsat případy záměny nástroje, vynechaných not, falešných not a posunutých nástupů. Výstup zůstává odhadem; univerzální přesnost pro směsi orchestru a popových aranží není zaručena.
- Uzavřít způsob, jak testující přijmou licenci modelových vah a jak se později naloží s případnou veřejnou či komerční verzí.

**Stav:** uživatel výslovně potvrdil, že veškeré použití vah v pilotu bude nekomerční; aplikace nabízí tři velikosti modelu. Výstupní audit kvality, seznam prakticky spolehlivých nástrojů a doporučená velikost modelu zůstávají otevřené do dodání skutečných skladeb a cílových počítačů.

### Etapa B — lokální engine jako oddělená služba

- Přidat adaptér mezi GUI a `muscriptor.cpp`; modelová inference nepoběží v hlavním GUI vlákně.
- Převod vstupu na formát modelu řešit přes existující dekodér, předat engine mono audio při 16 kHz a přijmout notové události: nástroj, MIDI výška, začátek, konec a další pole, která engine skutečně poskytuje.
- Zpracování po 5sekundových blocích zobrazovat jako průběh s možností zrušení; ukládat hotové bloky tak, aby šlo při přerušení pokračovat bez opakování celé skladby.
- Model stáhnout na vyžádání do cache aplikace, ověřit stažený soubor a ukázat velikost, zvolený výpočetní prostředek a průběh. Modelové soubory nebudou součástí EXE/DMG.
- Nezávisle ověřit Windows, macOS Apple Silicon a macOS Intel. Pro nepodporované GPU musí fungovat CPU fallback a srozumitelný stav.

**Stav:** implementováno a Linuxový C++ wrapper sestaven; skutečná inference na testovací nahrávce zůstává neověřena.

### Etapa C — datový formát projektu a MIDI import/export

- Přidat volitelnou sekci `music_analysis` do projektového JSONu: verze schématu, engine/model/verze, datum, délka a vzorkovací frekvence zdroje, stopy, noty, aktivita a stav uživatelské revize.
- Uložit notu jako minimálně `id`, `instrument`, `pitch`, `start_seconds`, `end_seconds` a případně `velocity` pouze tehdy, pokud ji engine skutečně poskytuje.
- Neukládat odhadovanou „confidence“ jako pravděpodobnost, pokud engine takový kalibrovaný údaj neposkytuje. Uložit zdroj a označení „AI návrh“.
- Přidat migraci verze 1 na novější formát tak, aby existující projekty, audio, reference a značky zůstaly beze změny.
- Přidat export a opětovný import standardního vícestopého MIDI; doplnit export CSV/JSON pro tabulkovou kontrolu.

**Stav:** implementováno: projekt JSON v2, zachování metadat/checkpointu, MIDI 0/1 import/export a CSV. MIDI kanálová kapacita se ověřuje před exportem.

### Etapa D — piano roll a mapa aktivity

- Do pracovního prostředí přidat oddělenou záložku **Hudební mapa**; původní přehrávač, waveform a značení zůstanou synchronizované.
- Vykreslit noty po stopách, výšku noty, taktovou mřížku, zoom, posun a playhead.
- Přidat filtrovatelné aktivity jako souhrn notových událostí za časový úsek; zobrazit také stávající YAMNet skóre jako samostatnou vrstvu, aby se modelové zdroje nepletly.
- Umožnit editaci not a změn v tabulce; podporovat undo/redo pro zásahy do not a světelných značek.
- Umožnit sólo/mute a srovnání původního audia s přehráním notové rekonstrukce.

**Stav:** implementováno v desktopu i webu: piano roll, tabulka, editace tažením, zoom, výběr instrumentu a filtr viditelné stopy. Undo/redo not a značek a samostatný export hudební mapy do PNG jsou dostupné v obou klientech. Zpětné přehrání not jako syntetického audia a pokročilé solo/mute zůstávají navazující rozšíření.

### Etapa E — světelné návrhy a tisk

- Z not a aktivit nabídnout kandidátní body: vstup/výstup vrstvy, nástup rytmiky, husté fill, změna hustoty a výrazné souběhy.
- Každý kandidát vytvořit jako běžnou editovatelnou značku s časem, nástrojem, důvodem a původem; deduplikovat blízké události a nabídnout prahové hodnoty.
- Uchovat ruční cue, AI návrhy, produkční pokyny a návrhy LD v oddělených kategoriích.
- Tiskový song sheet ponechat přehledný: strana 1 dostane zhuštěnou mapu aktivity a ověřené časové body; detailní piano roll exportovat zvlášť jako vícestránkovou přílohu podle taktů.

**Stav:** implementováno: editovatelné návrhy nástupů vrstev a hustých běhů not, s důvodem i původem a s časem na 25 fps. Desktop i web exportují samostatný PNG piano rollu; vícestránkový tisk podle taktů zůstává navazující práce.

### Etapa F — webová a desktopová shoda

- Desktopová verze bude první cílová implementace inference, protože může spouštět nativní lokální engine.
- Webový editor dostane stejné datové schéma, piano roll, aktivitu a editaci značek.
- Pro webový editor nejprve podporovat import MIDI/JSON z desktopu nebo NeuralNote. Pro přímou lokální inference z webové stránky připojit volitelný místní pomocný proces na `localhost`, který audio zpracuje na počítači.
- Hosted web nebude posílat produkční audio na server. Připojení k pomocnému procesu musí být výslovné a stav sítě viditelný.

**Stav:** datový formát, MIDI import/export, piano roll, filtrované kandidáty, undo/redo a PNG export mapy jsou v nasazeném testovacím editoru Sites v11; desktop má stejné editace a PNG export. LD cuebook a jeho předání jsou zachovány. Synchronizaci projektů přes cloud ani upload audia web neprovádí.

### Etapa G — uzavřený pilot a připravenost

- Pilot provést na různých aranžích, celých stopách a dostupném Windows/macOS hardwaru.
- Ověřit záměnu instrumentů a not poslechem, úpravy gridu, načtení uloženého projektu, MIDI export, dlouhé analýzy, přerušení a obnovu.
- Ověřit síťové chování: audio zůstává lokální; síť se použije pouze pro aktualizaci nebo stažení uživatelem vyžádaného modelu.
- Zaznamenat známá omezení a vytvořit krátký postup pro kontrolu výstupu při zkoušce.

**Stav:** čeká na skladby a fyzické Windows/macOS cíle. Bez nich nelze poctivě potvrdit přesnost, dobu analýzy, obnovu dlouhého přepisu ani kompatibilitu instalátorů.

## 6. Akceptační kritéria

- Celá skladba se analyzuje bez nahrávání audia na vzdálený server.
- Rozpoznané nástroje mají samostatné stopy a noty jsou časově zarovnané s přehrávaným audiem.
- Grid, waveform, playhead, tabulka a značky sdílejí jednu časovou osu; cue časové kódy zůstávají v 25 fps.
- Uživatel může noty i značky přidat, posunout, změnit a odstranit; přehrávání jde filtrovat po nástroji.
- Aktivita je jasně označená jako odvozená z přepisu nebo skóre konkrétního modelu.
- Projekty starší verze se otevřou bez ztráty dat; nový projekt přenese noty, aktivitu a zdrojové údaje.
- Tiskový PDF/PNG zůstane čitelný a detailní piano roll lze tisknout jako samostatnou přílohu.
- U každého automatického návrhu je zobrazen důvod a uživatel jej musí potvrdit nebo upravit.

## 7. Rozšíření po pilotu

1. Detailnější oddělení nástrojů a analýza jednotlivých stemů, pokud je přínos potvrzený na pilotních skladbách.
2. Taktová a proměnlivá beat mapa, chord/key odhady a detekce hudebních částí v jedné společné ose.
3. Jemnější mapa bicích/perkusí, akcentů, hlasitosti a instrumentálních nástupů pro návrhy cue.
4. Vícestránkový tisk piano rollu s možností volby nástrojů, taktového rozsahu a hustoty not.
5. Export značek do CSV šablony pro programování a zkoušky na grandMA2/MA3; přímé síťové ovládání světel ponechat mimo první rozsah.
6. Knihovna revidovaných projektů a srovnání AI návrhu s ručně opraveným výsledkem pro interní zlepšování procesu.

## 8. Hlavní rizika a rozhodnutí

- **Přesnost:** převod plného mixu na noty může zaměnit podobné barvy zvuku nebo vytvářet a vynechat noty. Proto se výstup upravuje a ověřuje poslechem.
- **Výkon a velikost:** větší modely potřebují více úložiště a GPU; nabídnout velikost modelu, viditelnou rychlost a CPU fallback.
- **Licence:** CC BY-NC 4.0 pokrývá nekomerční použití modelových vah. Veřejné vydání aplikace v0.3.0 váhy neobsahuje; komerční použití vah nebo jejich přibalení vyžaduje novou licenční kontrolu nebo jiný model.
- **Webová inference:** statická stránka nemůže sama spustit nativní C++ engine. Pro první webový pilot použít import notových událostí; přímé lokální zpracování vyžaduje instalovaný companion proces nebo samostatně ověřenou browserovou implementaci.
- **Časová přesnost:** výstup modelu není produkční timecode. Uchovávat čas not v sekundách a samostatně převádět LD značky na 25 fps.

