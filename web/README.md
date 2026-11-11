# StarDance SongSheet Studio · Web

Lokální editor pro prohlížeč. Spusťte `Start_Web_Editor.cmd` ve Windows nebo spusťte z kořenové složky projektu:

Aktuální zdrojové vydání desktopu i webu je [v0.3.0](https://github.com/lightingcze/StarDance_SongSheet_Studio/releases/tag/v0.3.0). Sdílený testovací editor Sites běží jako v11: [stardance-songsheet-studio-test](https://stardance-songsheet-studio-test.ondrabylok.chatgpt.site).

```bash
python -m http.server 8765 --bind 127.0.0.1
```

Pak otevřete `http://127.0.0.1:8765/web/`. Server pouze poskytuje statické soubory přes localhost.

## Funkce

- Desktopové rozhraní, náhled dvou stran A4 a export PDF/PNG.
- Přenosný projekt JSON, audio přehrávač, waveform a editovatelné značky s časováním 25 fps.
- Více stopový piano roll a odvozená aktivita po notových stopách; MIDI 0/1 a CSV import/export.
- Přesná editace not tažením i v tabulce; viditelné stopy i LD kandidáty lze filtrovat na vybraný instrument. Změny not i značek lze vrátit/zopakovat a mapu uložit do PNG.
- YAMNet/AudioSet časové skóre nástrojových tříd v úsecích po 0,48 s.
- Rozpoznání 7/10sekundového vzorku specializovaným klasifikátorem a volitelné oddělení čtyř vrstev přes SCNet.
- Volitelná identifikace skladby přes AcoustID s fingerprintem a uživatelským API klíčem.

Audio, obrázky i podporovaná inference běží v prohlížeči. Nativní MuScriptor se ve webové stránce nespouští; notový přepis z desktopového enginu přeneste jako MIDI. Při spuštění konkrétní analýzy může prohlížeč stáhnout běhovou knihovnu nebo model od uvedených poskytovatelů; samotné audio se při těchto analýzách neodesílá. Pokud uživatel výslovně spustí AcoustID, službě odejde akustický fingerprint, ne zvuk. Bezplatná služba AcoustID je určena pro nekomerční použití.

Skóre modelů nejsou kalibrované pravděpodobnosti ani izolované zvukové stopy. Třídy, časové značky a oddělené vrstvy ověřte poslechem. Licence a odkazy na modely jsou uvedeny přímo v editoru a v `../THIRD_PARTY_NOTICES.md`.
