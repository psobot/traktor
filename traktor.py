import numpy, sys, time, os, math, re

import echonest.audio as audio
from echonest import modify
from echonest.selection import *
from echonest.sorting import *
from cgi import escape as xmlescape
from pprint import pprint
from lxml import etree

class TraktorDB:
    original = ""  #   original XML data to ensure that collection has not been changed while we're working
    data = None
    path = "/Users/psobot/Documents/Native Instruments/Traktor 2.0.3/collection.nml"
    header = '<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n'

    def __init__(self, path=None):
        if path:
            self.path = path
        l = open(self.path, "r")
        self.original = l.read()
        l.close()

        #   Check this before saving - if the contents of the file do not match
        #   the contents of original, something has changed and we're out of sync!
        self.data = etree.parse(self.path)        

    def isConsistent(self):
        l = open(self.path, "r")
        current_xml = l.read()
        l.close()
        return current_xml == self.original

    def save(self):
        if self.isConsistent():
            xml = self.header + etree.tostring(self.data)
            l = open(self.path, "w")
            l.write(xml)
            l.close()
            self.original = xml
        else:
            raise Exception("Traktor database has changed!")

    def generateCues(self, track, replace=False):
        if not self.isConsistent():
            raise Exception("Traktor database has changed!")
        if not isinstance(track, etree._Element):
            track = self.getTracksByName(track)
            if len(track) > 1:
                raise Exception("Multiple tracks with that name!")
            else:
                track = track[0]
        if not track.get("AUDIO_ID"):
            raise Exception("Track has not been analyzed by Traktor!")

        if not replace and len(track.findall("CUE_V2")) - 1:   #   ignore the usual Autogrid cue
            raise Exception("Track already has cues!")

        #   TODO: Fix this to work on more than mac
        location =  track.find("LOCATION")
        localpath = "/Volumes/" + location.get("VOLUME") + location.get("DIR").replace("/:", "/") + location.get("FILE")

        song = audio.LocalAudioFile(localpath)
        os.unlink(song.convertedfile)

        offset = 0  #   used when the echonest thinks a song starts with a rest

        if track.findall("CUE_V2") and track.findall("CUE_V2")[0].get("NAME") == "AutoGrid":
            #   make use of Traktor's autogrid start point if it exists
            if (song.analysis.beats[0].start * 1000) < float(track.findall("CUE_V2")[0].get("START")):
                offset = (float(track.findall("CUE_V2")[0].get("START"))/1000 - song.analysis.beats[0].start)
                print "EchoNest thinks that the song starts with a rest. Offsetting by %s." % offset        # remove second cue then!!! 2nd cue is redundant
            for cue in track.findall("CUE_V2")[1:]:     #   Leave first cue, grid cue
                track.remove(cue)
        else:
            for cue in track.findall("CUE_V2"):
                track.remove(cue)

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
                if abs(beat.start - section.start) < closestDistance:
                    closestBeat = beat
                    closestDistance = abs(beat.start - section.start)
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
            cueElement = etree.Element("CUE_V2")
            #<CUE_V2 NAME="AutoGrid" DISPL_ORDER="0" TYPE="4" START="74.359565676842521" LEN="0" REPEATS="-1" HOTCUE="0"></CUE_V2>
            cueElement.set("NAME", "Section " + str(i + 1))
            cueElement.set("DISPL_ORDER", str(0))
            cueElement.set("TYPE", str(0))
            cueElement.set("LEN", str(0))
            cueElement.set("REPEATS", str(-1))
            cueElement.set("HOTCUE", str(i + 1))
            cueElement.set("START", str(cue['start'] * 1000))
            track.append(cueElement)

        self.save()
        return track.findall("CUE_V2")

    def getTrackByPath(self, path):
        #   Currently only works most-reliably on Mac...
        filename = os.path.basename(path)
        results = self.data.findall("COLLECTION/ENTRY/LOCATION[@FILE='%s']" % filename)
        if len(results) > 1:
            pathComponents = re.search("/Volumes/(.+?)/(.+?)/(.+?)" % filename, os.path.abspath(path))
            print "[DEBUG] pathComponents:", pathComponents
            if pathComponents:
                pathComponents = pathComponents.groups()
                volume = pathComponents[0]
                traktorDir = pathComponents[1].replace("/", "/:")
                parsedFilename = pathComponents[2]

                result = self.data.find("COLLECTION/ENTRY/LOCATION[@DIR='%s']" % traktorDir)
                if not result:
                    raise Exception("Track with path not found!")
                else:
                    return result
            else:
                #   Gotta fix this to work on more than external mac drives. Really...
                raise Exception("Multiple results for filename, and filepath parsing failed!")
        elif len(results):
            return results[0]
        else:
            raise Exception("Track with path '%s' not found!" % path)

    def getTracksByName(self, name):
        #   Quickly check for full name with the fast method...
        r = self.data.findall("COLLECTION/ENTRY[@TITLE='%s']" % name)
        if r:
            return r
        else:
            raise Exception("Tracks with name '%s' not found!" % name)

    def getAvailableTracks(self):
        #   Quickly check for full name with the fast method...
        r = self.data.xpath("COLLECTION/ENTRY[@AUDIO_ID][count(CUE_V2) = 1]")
        if r:
            return r
        else:
            raise Exception("No tracks available to add cues for!")

    def prettyPrintTracks(self, tracklist=None):
        if not tracklist:
            tracklist = self.getAvailableTracks()
        for track in tracklist:
            playtime = track.find("INFO").get("PLAYTIME")
            if playtime:
                playtime = int(playtime)
                secs = playtime % 60
                mins = int(playtime/60)
            else:
                mins = 0
                secs = 0
            print "\"%s\" by %s (%d:%02d)" % (track.get("TITLE"), track.get("ARTIST"), mins, secs )


    def searchForTracksByName(self, name):
        r = self.data.xpath("COLLECTION/ENTRY[contains(@TITLE, '%s')" % name)
        if r:
            return r
        else:
            raise Exception("Tracks containing '%s' not found!" % name)


    def getTracksByArtist(self, name):
        r = self.data.findall("COLLECTION/ENTRY[@ARTIST='%']" % name)
        if r:
            return r
        else:
            raise Exception("Tracks with artist '%s' not found!" % name)

db = TraktorDB()
#filename = "/Volumes/Fry HD/Music/iTunes/iTunes Music/Battles/Gloss Drop/03 Futura.mp3"
#db.generateCues(filename)
