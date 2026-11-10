# StarDance SongSheet Studio · Web

Lokální editor pro prohlížeč. Spusťte `Start_Web_Editor.cmd` ve Windows nebo spusťte z kořenové složky projektu:

```bash
python -m http.server 8765 --bind 127.0.0.1
```

Pak otevřete `http://127.0.0.1:8765/web/`. Server pouze poskytuje statické soubory přes localhost.

## Funkce

- Desktopové rozhraní, náhled dvou stran A4 a export PDF/PNG.
- Přenosný projekt JSON, audio přehrávač, waveform a editovatelné značky s časováním 25 fps.
- YAMNet/AudioSet časové skóre nástrojových tříd v úsecích po 0,48 s.
- Rozpoznání 7/10sekundového vzorku specializovaným klasifikátorem a volitelné oddělení čtyř vrstev přes SCNet.
- Volitelná identifikace skladby přes AcoustID s fingerprintem a uživatelským API klíčem.

Audio, obrázky i inference běží v prohlížeči. Při spuštění konkrétní analýzy může prohlížeč stáhnout běhovou knihovnu nebo model od uvedených poskytovatelů; samotné audio se při těchto analýzách neodesílá. Pokud uživatel výslovně spustí AcoustID, službě odejde akustický fingerprint, ne zvuk. Bezplatná služba AcoustID je určena pro nekomerční použití.

Skóre modelů nejsou kalibrované pravděpodobnosti ani izolované zvukové stopy. Třídy, časové značky a oddělené vrstvy ověřte poslechem. Licence a odkazy na modely jsou uvedeny přímo v editoru a v `../THIRD_PARTY_NOTICES.md`.
