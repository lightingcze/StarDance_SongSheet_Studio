# StarDance SongSheet Studio

Lokální desktopový editor pro tiskové hudební song sheety StarDance. Vytváří dvě strany A4 na šířku pro každou skladbu a exportuje PDF nebo dvojici PNG v tiskovém rozlišení.

**Vydání:** [StarDance SongSheet Studio v0.3.0](https://github.com/lightingcze/StarDance_SongSheet_Studio/releases/tag/v0.3.0) · 11. 11. 2026

Přehled změn jednotlivých vydání je v [CHANGELOG.md](CHANGELOG.md).

## Funkce

- Import WAV, MP3, FLAC, M4A, AAC, OGG a AIFF.
- Stereo přehrávání zdrojového audia přímo v editoru pro poslechovou kontrolu.
- Přehrávač přímo v editoru, playhead s aktuálním 25fps časem a klikací waveform pro posun.
- Značky lze přidávat a odebírat, přetahovat po waveformu a upravovat přímo v tabulce (název, typ i čas); úpravy značek a not lze vrátit nebo zopakovat.
- Waveform ze skutečného načteného audia, délka a automatický odhad BPM.
- Návrhy akcentů a energetických oken s časovými značkami `HH:MM:SS:FF` při 25 fps.
- Heuristický odhad nástrojových vrstev a kandidátní značky pro perkuse, bas/kopák a tónové vrstvy.
- Volitelný lokální rozbor YAMNet/AudioSet se skóre aktivity nástrojových tříd v časových úsecích po 0,48 s.
- Časový přehled rozpoznaných tříd, filtr značek podle nástroje a přidání kandidátních značek ze zvoleného filtru.
- Celý mix lze volitelně přepsat místním modelem MuScriptor na noty podle instrumentů; hotové bloky lze po přerušení obnovit.
- Více stopový piano roll: čas, výška, délka a odvozená hustota not po stopách; noty lze přidat, posunout, přetáhnout, změnit v tabulce, odstranit a vrátit či zopakovat jejich úpravy.
- Import/export standardního vícestopého MIDI a CSV not; MIDI projekty z aplikace nebo NeuralNote lze otevřít ve webové verzi.
- Samostatný export hudební mapy s piano rollem do PNG; ve webové i desktopové verzi.
- Filtr piano rollu podle vybrané instrumentální stopy; LD kandidáty lze generovat ze všech nebo jen zobrazených stop.
- Kandidátní LD značky lze vytvořit z nástupů instrumentálních vrstev a zhuštěných běhů not. Zůstávají editovatelnými návrhy.
- Editor skladby, interpreta, účinkujících, tance, produkčních poznámek a vlastních návrhů LD.
- Vložení až čtyř obrazových referencí na druhou stranu.
- Nastavitelná barva, světlý/tmavý vzhled a zobrazení waveformu či referencí.
- Přenosný projekt JSON, který při uložení zkopíruje audio a reference do složky vedle projektu.
- Export dvoustránkového PDF a dvou tiskových PNG.

## Spuštění ze zdrojů

Vyžaduje Python 3.10 nebo novější a instalaci Tkinteru pro daný systém.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Na Linuxu může být Tkinter potřeba doinstalovat z balíčků distribuce. Zvuk se analyzuje lokálně. Při prvním spuštění YAMNet aplikace stáhne model a seznam tříd; samotné audio se do sítě neposílá.

## Vytvoření aplikace

- Windows: v PowerShellu spusťte `packaging/build_windows.ps1`. Výsledkem je `dist/StarDanceSongSheet.exe`.
- macOS: spusťte `packaging/build_macos.command`. Výsledkem je `dist/StarDanceSongSheet-macOS.dmg`.
- GitHub Actions: workflow `Build desktop packages` sestaví oba cíle a přiloží EXE a DMG jako artefakty běhu. Tag `v*` nebo push na větev `release/v*` vytvoří GitHub Release s oběma instalátory.

Windows a macOS balíčky se sestavují na příslušném systému v GitHub Actions. Aktuální EXE a DMG jsou v [GitHub Releases](https://github.com/lightingcze/StarDance_SongSheet_Studio/releases). Mac aplikace není podepsaná ani notarizovaná; Gatekeeper může při prvním spuštění zobrazit potvrzení. Windows EXE také není podepsané certifikátem vydavatele.

## Použití

1. Zvolte **Načíst audio**. Waveform a hudební odhady se načtou na pozadí.
2. V kartách editoru doplňte údaje o skladbě, produkční zadání a vlastní návrhy LD.
3. Na kartě **Audio a značky** přehrávejte skladbu, klikněte do waveformu pro posun a přidejte vlastní časové značky. Volitelně spusťte **Analyzovat nástroje v čase (YAMNet)**; časová osa zobrazí skóre shody AudioSet tříd v úsecích po 0,48 s. Použijte filtr vrstvy nebo **Značky z odhadu**; značky upravíte tažením nebo dvojklikem do buňky tabulky.
4. Na kartě **Hudební mapa** vyberte velikost MuScriptoru a spusťte **AI přepis celé skladby**. Audio se dekóduje a zpracuje lokálně; vybraný model se stáhne jen při prvním použití a ověří se SHA-256. Malý model má přibližně 209 MB, střední 618 MB a velký 2,74 GB. Výstup se dělí po 5 sekundách; hotové bloky zůstávají v projektu při přerušení. Prohlížejte a upravujte noty v piano rollu a tabulce. Vraťte nebo zopakujte poslední úpravu tlačítky **Zpět/Znovu** nebo Ctrl+Z / Ctrl+Y (na macOS Cmd+Z / Cmd+Shift+Z); textová pole zachovávají vlastní systémové vracení. Pro vlastní lokální běh ze zdrojů nejprve sestavte C++ engine podle `native/CMakeLists.txt` (CMake 3.24+, C++23 a Ninja; macOS vyžaduje Xcode).
5. Vložte vizuální reference a dolaďte vzhled stránky.
6. Přepínejte náhled mezi stranou 1 (hudba) a stranou 2 (produkce).
7. Uložte JSON projekt a exportujte PDF nebo PNG.

Produkční pole jsou určena pro věrný přepis podkladů. Návrhy LD mají samostatnou barevně označenou oblast. Automatické BPM, energetická okna, nástrojové vrstvy i kandidátní akcenty jsou pouze odhady. Frekvenční heuristika neumí oddělit jednotlivé stopy ani spolehlivě rozlišit například basu od kopáku či klávesy od kytary. YAMNet/AudioSet přidává konkrétnější časové skóre zvukových tříd, ale skóre není kalibrovaná pravděpodobnost ani izolovaná stopa. Takt, první doby, fráze, instrumentaci a GO cue vždy ověřte poslechem.

## Poznámky k měření

Tempo se hledá z krátké RMS obálky. Základní nástrojové vrstvy se odhadují z frekvenčních pásem, spektrální plochosti a transientů; volitelný YAMNet/AudioSet vytváří skóre shody rozpoznaných tříd po 0,48 s a kandidátní časové úseky. Tlačítko **Značky z odhadu** vytvoří editovatelné časové kandidáty, které lze filtrovat podle vrstvy. Waveform ukazuje relativní špičkovou úroveň nahrávky. Energetické úseky jsou desetisekundová okna hlasitosti, nikoli rozpoznané hudební fráze. Časové kódy jsou zaokrouhleny na nejbližší snímek při 25 fps. Aplikace nenahrazuje poslechovou kontrolu ani provozní ověření cue na zkoušce.

MuScriptor vytváří nástupy, délky, výšky tónů a instrumentální programy; nevytváří velocity, BPM, takt ani jistotu jednotlivých not. Výchozí velocity 96 při exportu MIDI je jen technická hodnota pro přehratelnost. Piano roll zachovává časy not v sekundách a taktovou mřížku používá jako vodítko. Notová aktivita je hustota not v čase, nikoli hlasitost instrumentu. Modelové váhy mají licenci CC BY-NC 4.0 a aplikace je nestahuje ani nepřikládá k instalátoru; uživatel je může získat pouze při spuštění analýzy. Kód `muscriptor.cpp` je připnut na commit `8589219cc3b584bce970f95aec2ec4a04e53b280`; omezení a licence jsou uvedeny v `THIRD_PARTY_NOTICES.md`.

Před prvním stažením modelu aplikace zobrazí licenční upozornění a vyžádá si potvrzení. Uživatel výslovně potvrdil výhradně nekomerční použití vah MuScriptoru v tomto pilotu. Veřejný zdrojový kód ani instalační balíčky modelové váhy neobsahují; uživatel si je stahuje samostatně jen po potvrzení nekomerčního použití. Před komerčním použitím vah nebo jejich přibalením k aplikaci je nutné znovu prověřit licenci.

## Licence písem

Vykreslování českého textu používá DejaVu Sans. Licenční text je v `assets/fonts/DEJAVU_FONT_LICENSE.txt`.

## Webová verze

Otevřete `Start_Web_Editor.cmd` nebo postupujte podle návodu v `web/README.md`. Webový editor běží místně v prohlížeči; audio a obrazové reference zůstávají na vašem zařízení. Hudební mapu lze exportovat samostatně do PNG. Vyžádané modely se stahují při prvním použití. Pokud výslovně spustíte AcoustID, službě odejde akustický fingerprint, ne audio.

Testovací webová verze je nasazena na [stardance-songsheet-studio-test](https://stardance-songsheet-studio-test.ondrabylok.chatgpt.site). Obsahuje LD cuebook a propojený SongSheet Studio editor s piano rollem; samotný webový editor načítá notové přepisy přes MIDI a nespouští nativní MuScriptor.
