Traktor(.py)
============

Python module for modifying Native Instruments' Traktor 2 database.

Allows for auto-generation of hotcue points (via the Echo Nest API) and basic searching of songs in Traktor's DB.

Written by Peter Sobot, July 16, 2011, at #sehackday #4.

http://github.com/psobot/traktornest

(Requires an Echo Nest Remix API key: http://code.google.com/p/echo-nest-remix/)

Usage
-----

How to automatically generate hotcue points for every Daft Punk song in your library:

```
tunes = traktor.TraktorDB()
for track in tunes.getTracksByArtist("Daft Punk"):
    tunes.generateCues(track)
tunes.save()
```
