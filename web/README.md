# StarDance SongSheet Studio · Web

Lokální webová verze editoru. Běží přímo v prohlížeči bez instalace balíčků, bez účtu a bez nahrávání souborů na server.

## Spuštění ve Windows

Z kořenové složky projektu spusťte Start_Web_Editor.cmd. Otevře se lokální stránka na adrese http://127.0.0.1:8765/web/. Server zůstane běžet v samostatném okně; po dokončení ho zavřete.

Python 3 musí být dostupný jako příkaz python. Alternativně:

    python -m http.server 8765 --bind 127.0.0.1

Pak otevřete http://127.0.0.1:8765/web/.

## Co webová verze umí

- Vyplnit skladbu, interpreta, účinkující, tanec, produkční zadání a návrhy LD.
- Načíst místní audio, přehrávat ho, posouvat playhead a procházet waveform se zoomem.
- Vytvářet a upravovat značky, přetahovat je ve waveformu a filtrovat podle vrstvy.
- Vytvořit kandidátní akcenty, energetická okna a orientační nástrojové vrstvy.
- Přidat až čtyři obrazové reference, upravit barevný vzhled a zobrazit dvě tiskové A4 stránky.
- Uložit přenosný projektový JSON včetně audia a referencí, exportovat dvě PNG a vytisknout či uložit dvoustránkové PDF přes dialog prohlížeče.

## Data a kompatibilita

Audio a obrázky se načítají a zpracovávají na vašem zařízení. Webová verze je samostatná statická stránka; server pouze zpřístupní soubory aplikace na 127.0.0.1. Pro audio analýzu je potřeba prohlížeč s Web Audio API. Podpora formátů závisí na kodecích daného prohlížeče; při problému zkuste WAV nebo MP3.

Pracovní formulář se ukládá do lokálního úložiště prohlížeče. Projektový JSON je přenosný a obsahuje přiložené audio a obrázky, takže může být velký. Existující desktopové projekty ve formátu stardance-songsheet lze otevřít pro údaje, značky a waveform; audio a obrazové soubory, na které odkazují cestou na disku, přidejte do webové verze znovu přes výběr souboru.

Webová verze je záměrně v čistém HTML, CSS a JavaScriptu bez závislostí. Rozhraní je v index.html, vzhled v styles.css a chování v app.js.
