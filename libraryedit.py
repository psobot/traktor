import numpy, sys, time, os, math, re

import echonest.audio as audio
from echonest import modify
from echonest.selection import *
from echonest.sorting import *
from cgi import escape as xmlescape
from pprint import pprint
from lxml import etree

def _distanceBetween(a, b):
    return abs(a.start - b.start)

class TraktorDBTrack:
    def __init__(self, xml, parent=None):
        self.parent = parent
        self.xml = xml
        self.original = self.xml
        self.title = re.search("<ENTRY.*?TITLE=\"(.+?)\".*?>", self.xml).groups()[0]
        artiststring = re.search("<ENTRY.*?ARTIST=\"(.+?)\".*?>", self.xml)
        if artiststring:
            self.artist = artiststring.groups()[0]
        else:
            self.artist = None
        
        pathComponents = re.search("<LOCATION DIR=\"(.+?)\" FILE=\"(.+?)\" VOLUME=\"(.+?)\" VOLUMEID=\".+?\"></LOCATION>", self.xml);
        if pathComponents:
            pathComponents = pathComponents.groups()
            directory = pathComponents[0].replace("/:", "/")
            filename = pathComponents[1]
            volume = pathComponents[2]
            self.path = "/Volumes/" + volume + directory + filename
        else:
            self.path = ""

        rawcues = re.findall("<CUE_V2 NAME=\"(.+?)\" DISPL_ORDER=\"\d+?\" TYPE=\"(\d)\" START=\"([-0-9.]+?)\" LEN=\"([-0-9.]+?)\" REPEATS=\"([-0-9.]+?)\" HOTCUE=\"(\d)\"></CUE_V2>", self.xml)
        self.cues = []

        #   put all cues into a list of our own formatting
        for cue in rawcues:
            self.cues.append(TraktorCue(*cue))

        #   remove all cues from existing XML
        self.xml = re.sub("<CUE_V2 NAME=\"(.+?)\" DISPL_ORDER=\"\d+?\" TYPE=\"\d\" START=\"([-0-9.]+?)\" LEN=\"([-0-9.]+?)\" REPEATS=\"([-0-9.]+?)\" HOTCUE=\"(\d)\"></CUE_V2>\s+?", "", self.xml)

    def update(self):
        if self.parent:
            self.parent.replace(self.original, str(self))
        else:
            raise Exception("Track not associated with a DB!")

    def save(self):
        if self.parent:
            self.parent.replace(self.original, str(self))
            self.parent.save()
        else:
            raise Exception("Track not associated with a DB!")

    def __str__(self):
        return re.sub("</ENTRY>", "".join([str(cue) for cue in self.cues]) + "</ENTRY>", self.xml)

    def __repr__(self):
        return "<TraktorDBTrack: \"%s\" by %s>" % (self.title, self.artist)

class TraktorCue:
    def __init__(self, name = "n.n.", cuetype = 0, start = 0, length = 0, repeats = -1, hotcue = 0):
        self.name = str(name)
        self.cuetype = int(cuetype)
        self.start = float(start)
        self.length = float(length)
        self.repeats = int(repeats)
        self.hotcue = int(hotcue)

    def __repr__(self):
        return str(self)[:-1]

    def __str__(self):
        return "<CUE_V2 NAME=\"%s\" DISPL_ORDER=\"0\" TYPE=\"%s\" START=\"%s\" LEN=\"%s\" REPEATS=\"%s\" HOTCUE=\"%s\"></CUE_V2>\n" % (self.name, self.cuetype, self.start, self.length, self.repeats, self.hotcue)

class TraktorDB:
    #   Yes, I am using regular expressions here to parse and edit XML.
    #   Yes, I realize this is heresy, and understand why.
    #   Traktor is very, very picky about the format of its NML file.
    #   No XML library can do what I need. Regex does, in this case.

    xml = ""       #   mutable XML data that we'll change 
    original = ""  #   original XML data to ensure that collection has not been changed while we're working
    path = "/Users/psobot/Documents/Native Instruments/Traktor 2.0.3/collection.nml"

    def __init__(self, path=None):
        if path:
            self.path = path
        l = open(self.path, "r")
        self.xml = l.read()
        l.close()

        #   Check this before saving - if the contents of the file do not match
        #   the contents of original, something has changed and we're out of sync!
        self.original = self.xml

        #   Init object with all tracks
        tracks = re.findall("(<ENTRY .+?>[\s\S]+?</ENTRY>)", self.xml)
        self.tracks = [TraktorDBTrack(track, self) for track in tracks]

    def isConsistent(self):
        l = open(self.path, "r")
        current_xml = l.read()
        l.close()
        return current_xml == self.original

    def save(self):
        if self.isConsistent():
            l = open(self.path, "w")
            l.write(self.xml)
            l.close()
            self.original = self.xml
        else:
            raise Exception("Traktor database has changed!")

    def generateCues(self, track, replace=False):
        if not self.isConsistent():
            raise Exception("Traktor database has changed!")
        if not isinstance(track, TraktorDBTrack):
            raise Exception("generateCues requires a TraktorDBTrack object.")
        if not track:
            raise Exception("Track not in Traktor database!")
        if not replace and len(track.cues):
            raise Exception("Track already has cues!")

        song = audio.LocalAudioFile(track.path)
        os.unlink(song.convertedfile)

        offset = 0  #   used when the echonest thinks a song starts with a rest

        if track.cues and track.cues[0].name == "AutoGrid":
            #   make use of Traktor's autogrid start point if it exists
            if (song.analysis.beats[0].start * 1000) < track.cues[0].start:
                offset = (track.cues[0].start/1000 - song.analysis.beats[0].start)
                print "EchoNest thinks that the song starts with a rest. Offsetting by %s." % offset        # remove second cue then!!! 2nd cue is redundant
            track.cues = track.cues[:1]     #   Leave first cue, grid cue
        else:
            track.cues = []

        #   Look ma, actual audio analysis!

        potentialCues = []
        
        print "Overall analysis confidence: %s" % (song.analysis.time_signature['confidence'])
        if song.analysis.time_signature['confidence'] < 0.5:
            print "Analysis not very confident - song may have bad cuepoints."

        firstbeats = song.analysis.beats[::song.analysis.time_signature['value']]   #   grab every nth beat
        beatlength = 60.0/song.analysis.tempo['value']

        #   Start by iterating through sections...
        for i, section in enumerate(song.analysis.sections):
            closestBeat = None
            closestDistance = song.analysis.duration
            for beat in firstbeats:   
                if _distanceBetween(beat, section) < closestDistance:
                    closestBeat = beat
                    closestDistance = _distanceBetween(beat, section)
            if closestBeat.start - offset > 0:
                potentialCues.append({"start": closestBeat.start + offset, "confidence": closestBeat.confidence})

        #   If we have more cues than hotcue spots available, then choose the top 7 most confident.
        if len(potentialCues) > 7:
            potentialCues = sorted(potentialCues, key=lambda k: k['confidence'])
            potentialCues = potentialCues[:7]
            potentialCues = sorted(potentialCues, key=lambda k: k['start'])
        
        for i, cue in enumerate(potentialCues):
            print "Confidence of cue %s: %s" % (i, cue['confidence'])

        for i, cue in enumerate(potentialCues):
            track.cues.append(TraktorCue("Section " + str(i + 1), hotcue=(i + 1), start=cue['start'] * 1000))

        track.save()
        return track.cues

    def replace(self, original, replace):
        self.xml = re.sub(re.escape(original), replace, self.xml)
    
    def getTrackByPath(self, path):
        for track in self.tracks:
            if track.path == path:
                return track
        raise Exception("Track with path '%s' not found!" % path)

    def getTracksByName(self, name):
        r = []
        for track in self.tracks:
            if track.title == name:
                r.append(track)
        if r:
            return r
        else:
            raise Exception("Tracks with name '%s' not found!" % name)

    def getTracksByArtist(self, name):
        r = []
        for track in self.tracks:
            if track.artist == name:
                r.append(track)
        if r:
            return r
        else:
            raise Exception("No tracks with artist '%s' found!" % name)


db = TraktorDB()
#filename = "/Volumes/Fry HD/Music/iTunes/iTunes Music/Battles/Gloss Drop/03 Futura.mp3"
#db.generateCues(filename)
