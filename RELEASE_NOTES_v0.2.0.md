# StarDance SongSheet Studio v0.2.0

## Novinky
- YAMNet/AudioSet časová analýza hudebních tříd po 0,48 s v desktopové aplikaci pro Windows a macOS.
- Filtrování nástrojových vrstev a vkládání kandidátních značek s uvedeným skóre a zdrojem.
- Uložení časové aktivity a důkazních údajů v přenosném projektu JSON.
- Webový editor synchronizovaný s aktuálním portálem: YAMNet časová osa, 7/10sekundová klasifikace vzorku, volitelné oddělení vrstev a AcoustID rozpoznání podle fingerprintu.
- Automatizované sestavení EXE a DMG při vydání.

## Poznámky
- Audio zůstává při YAMNet analýze na zařízení. Model a seznam tříd se stáhnou při prvním spuštění.
- Skóre jsou kandidáty zvukových tříd, nikoli kalibrované pravděpodobnosti ani izolované stopy; ověřujte poslechem.
- AcoustID je v prohlížečovém editoru volitelné a odesílá fingerprint pouze po spuštění rozpoznání.
- Windows EXE není podepsané a macOS DMG není podepsané ani notarizované.
