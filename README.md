# StarDance SongSheet Studio

Lokální desktopový editor pro tiskové hudební song sheety StarDance. Vytváří dvě strany A4 na šířku pro každou skladbu a exportuje PDF nebo dvojici PNG v tiskovém rozlišení.

## Funkce

- Import WAV, MP3, FLAC, M4A, AAC, OGG a AIFF.
- Stereo přehrávání zdrojového audia přímo v editoru pro poslechovou kontrolu.
- Přehrávač přímo v editoru, playhead s aktuálním 25fps časem a klikací waveform pro posun.
- Značky lze přidávat a odebírat, přetahovat po waveformu a upravovat přímo v tabulce (název, typ i čas).
- Waveform ze skutečného načteného audia, délka a automatický odhad BPM.
- Návrhy akcentů a energetických oken s časovými značkami `HH:MM:SS:FF` při 25 fps.
- Heuristický odhad nástrojových vrstev a kandidátní značky pro perkuse, bas/kopák a tónové vrstvy.
- Filtr značek podle vrstvy a automatické přidání časových kandidátů z nástrojového odhadu.
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

Na Linuxu může být Tkinter potřeba doinstalovat z balíčků distribuce. Aplikace zpracovává soubory lokálně a neposílá je do sítě.

## Vytvoření aplikace

- Windows: v PowerShellu spusťte `packaging/build_windows.ps1`. Výsledkem je `dist/StarDanceSongSheet.exe`.
- macOS: spusťte `packaging/build_macos.command`. Výsledkem je `dist/StarDanceSongSheet-macOS.dmg`.
- GitHub Actions: workflow `Build desktop packages` sestaví oba cíle a přiloží EXE a DMG jako artefakty běhu. Push tagu ve tvaru `v*` navíc vytvoří GitHub Release s oběma soubory.

Windows a macOS balíčky se musí sestavit na příslušném systému. Tento zdrojový projekt lze sestavit přes GitHub Actions po přidání do repozitáře. Mac aplikace není podepsaná ani notarizovaná; Gatekeeper může při prvním spuštění zobrazit potvrzení. Windows EXE také není podepsané certifikátem vydavatele.

## Použití

1. Zvolte **Načíst audio**. Waveform a hudební odhady se načtou na pozadí.
2. V kartách editoru doplňte údaje o skladbě, produkční zadání a vlastní návrhy LD.
3. Na kartě **Audio a značky** přehrávejte skladbu, klikněte do waveformu pro posun a přidejte vlastní časové značky. Použijte filtr vrstvy nebo **Značky z odhadu**; značky upravíte tažením nebo dvojklikem do buňky tabulky.
4. Vložte vizuální reference a dolaďte vzhled stránky.
5. Přepínejte náhled mezi stranou 1 (hudba) a stranou 2 (produkce).
6. Uložte JSON projekt a exportujte PDF nebo PNG.

Produkční pole jsou určena pro věrný přepis podkladů. Návrhy LD mají samostatnou barevně označenou oblast. Automatické BPM, energetická okna, nástrojové vrstvy i kandidátní akcenty jsou pouze odhady. Frekvenční heuristika neumí oddělit jednotlivé stopy ani spolehlivě rozlišit například basu od kopáku či klávesy od kytary. Takt, první doby, fráze, instrumentaci a GO cue vždy ověřte poslechem.

## Poznámky k měření

Tempo se hledá z krátké RMS obálky. Nástrojové vrstvy se odhadují z frekvenčních pásem, spektrální plochosti a transientů. Tlačítko **Značky z odhadu** vytvoří časové kandidáty, které lze filtrovat podle vrstvy. Waveform ukazuje relativní špičkovou úroveň nahrávky. Energetické úseky jsou desetisekundová okna hlasitosti, nikoli rozpoznané hudební fráze. Časové kódy jsou zaokrouhleny na nejbližší snímek při 25 fps. Aplikace nenahrazuje poslechovou kontrolu ani provozní ověření cue na zkoušce.

## Licence písem

Vykreslování českého textu používá DejaVu Sans. Licenční text je v `assets/fonts/DEJAVU_FONT_LICENSE.txt`.
