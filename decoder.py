import sys
import mutagen
import os
import struct
from pprint import pprint
import eyeD3
from zlib import crc32, adler32
import md5
import crc16

if len(sys.argv) < 1:
    usage()
    exit(1)

def t_string_decode(data):   # "traktor string" decoder
    return "".join(data[4::2])

def padhex(number):
    c = hex(number)[2:]
    if len(c) == 1:
        c = '0'+c
    return str(c)

def traktor_string(string):
    return struct.pack("<L"+(len(string) * "cx"), len(string), *[c for c in string])

def decode(ls, depth, offset, data, **kwargs):
    t_id_1, t_id_2, t_id_3, t_id_4, t_len, children = struct.unpack_from("<"+("x" * offset)+"cccc L L", data);
    t_len = int(t_len);
    t_id = str(t_id_1) + str(t_id_2) + str(t_id_3) + str(t_id_4)

    offset += 12; #length of my header.. data or another container follows
    pcdl = 0;  #previous child data length

    #indentation?
    if not "n" in kwargs:
        pass#print "\t" * depth,

    #names backwards?
    t_di = t_id[::-1];
    if "o" in kwargs:
        pass#print t_id,
    else:
        pass#print t_di,
    
    value = False

    if not(children): #this is data item, not a container

        #interpret value if possible
        if "r" in kwargs:
            t_l2 = t_len * 2;
            t_value = struct.unpack_from("<"+str(offset)+"x H"+str(t_l2), data);
            print " raw:"+str(t_value),

        else:
            interpreted = "";
            if t_di == "VRSN" or t_di == "BITR" or t_di == "TNMO" or t_di == "FLGS" or t_di == "FLGS" or t_di == "RANK" or t_di == "PCNT" or t_di == "TRCK":
                #version..
                interpreted = str(struct.unpack_from("<"+str(offset)+"x l", data)[0]);
                value = interpreted                
            elif t_di == "BPMT" or t_di == "BPMQ" or t_di == "HBPM" or t_di == "PKDB" or t_di == "PCDB":
                #BPM
                interpreted = struct.unpack_from("<"+str(offset)+"x f", data)[0];
                value = interpreted
            elif t_di == "CUEP":
                #cue points..
                #output number of cue points
                t_cuepoints = struct.unpack_from("<"+str(offset)+"x l", data)[0];
                value = []
                #offset used for individual cuepoints, skip 4 bytes (number of cuepoints)
                t_cueoff = offset + 4;
                for i in xrange(t_cuepoints):
                    interpreted += "\n";
                    #indentation
                    if not("n" in kwargs):
                        interpreted += "\t" * (depth + 1);

                    interpreted += "CUE"+str(i+1);
                    #first long should be 1 ..?
                    t_first = struct.unpack_from("<"+str(t_cueoff)+"x l", data)[0];
                    if t_first != 1:
                        interpreted += " Cue format not recognized: "+str(t_first);
                        value.append(False)
                    else:
                        #skip the first long
                        t_cueoff += 4;

                        #cuepoint name, stored as "traktor string"
                        t_namelen = struct.unpack_from("<"+str(t_cueoff)+"x l", data)[0];

                        #namestring length: long (length of string) + 2 * string length
                        t_namestrlen = 4 + t_namelen * 2;
                        name = t_string_decode(struct.unpack_from("<"+str(t_cueoff)+"x "+str(t_namestrlen)+"c", data))
                        interpreted += " " + name;

                        #add to the offset: namestring length
                        t_cueoff += t_namestrlen;

                        #rest of the cuepoint contents
                        (t_displ_order, t_type, t_start, t_len2, t_repeats, t_hotcue) = struct.unpack_from("<"+str(t_cueoff)+"x l l d d l l", data);

                        #type translated
                        t_type_t = t_type;
                        if(t_type == 0):
                            t_type_t = "CUE";
                        elif(t_type == 1):
                            t_type_t = "IN";
                        elif(t_type == 2):
                            t_type_t = "OUT";
                        elif(t_type == 3):
                            t_type_t = "LOAD";
                        elif(t_type == 4):
                            t_type_t = "GRID";
                        elif(t_type == 5):
                            t_type_t = "LOOP";

                        interpreted += ", displ_order: "+str(t_displ_order)+", type: "+str(t_type_t)+", start: "+str(t_start)+", len: "+str(t_len)+", repeats: "+str(t_repeats)+", hotcue: "+str(t_hotcue);
                        value.append({"name": name, "order": t_displ_order, "type": {"number": t_type, "name": t_type_t}, "start": t_start, "length": t_len2, "repeats": t_repeats, "hotcue": t_hotcue})
                        #lengh of the rest
                        t_cueoff += 32;
            elif(t_di == "TLEN"):
                #track length
                interpreted = struct.unpack_from("<"+str(offset)+"x l", data)[0];
                value = interpreted
                t_sec = interpreted % 60
                if t_sec < 10:
                    t_sec = "0"+str(t_sec)
                interpreted = str(int(int(interpreted/60))) + ":" + str(t_sec)
            elif t_di == "TIT1" or t_di == "TIT2" or t_di == "TALB" or t_di == "TCON" or t_di == "TCOM" or t_di == "COMM" or t_di == "TPE1" or t_di == "TPE4" or t_di == "LABL" or t_di == "TKEY" or t_di == "USLT":
                interpreted = t_string_decode(struct.unpack_from("<"+str(offset)+"x "+str(t_len)+"c", data));
            elif t_di == "RLDT" or t_di == "IPDT" or t_di == "LPDT" or t_di == "FMOD":
                interpreted = "/".join([str(c) for c in struct.unpack_from("<"+str(offset)+"x b b H", data)]);
            
            if not value:
                value = interpreted
            
            if interpreted != "":
                pass#print interpreted,
            else:
                #print raw, truncate to 60 characters..
                t_l2 = int(t_len);
                #print "t_l2:", t_l2, " offset:", offset, "ll:", ll;
                t_value = struct.unpack_from("<"+str(offset)+"x "+str(int(t_l2))+"B", data);
                #print " 0x"+"".join(padhex(t) for t in t_value[:30]),
                value = t_value    #this line makes lots of datas
                if(t_len > 30):
                    pass#print "...",
        ls[t_di] = value
    #print "\n",

    #if this is not a data node (ie children > 0)
    #iterate through all children and descend recursively
    for i in xrange(0, children):
        n = {}
        pcdl += 12 + decode(n, depth + 1, offset + pcdl, data);
        #print "N",  n
        #print "ls", ls
        #print "t_di", t_di
        if not t_di in ls:
            ls[t_di] = n
        else:
            ls[t_di].update(n)

    #returns length of the current item so the next iteration can add it to the offset
    return(t_len);

def encode(key, value):
    if isinstance(value, dict):     #hierarchy
        s = ""
        for k, v in value.iteritems():
            string = encode(k, v);
            #print len(string), k, [string]
            s += string
        return struct.pack("<cccc L L", key[3], key[2], key[1], key[0], len(s), len(value)) + s
    elif isinstance(value, list):   #Cue Point List
        s = ""
        for k, v in enumerate(value):
            s += struct.pack("<L", 1) + traktor_string(v['name']) + struct.pack("<l l d d l l", v['order'], v['type']['number'], v['start'], v['length'], v['repeats'], v['hotcue'])
        return struct.pack("<cccc L xxxx L", key[3], key[2], key[1], key[0], len(s) + 4, len(value)) + s
    else:   #leaf
        val = ""
        if key == "VRSN" or key == "FLGS" or key == "RANK" or key == "TNMO" or key == "TLEN" or key == "TRCK" or key == "BITR":
            val = struct.pack("<l", int(value))
        elif key == "BPMT" or key == "BPMQ" or key == "HBPM" or key == "PCDB" or key == "PKDB":
            val = struct.pack("<f", float(value))
        elif key == "COMM" or key == "TALB" or key == "TCON" or key == "TIT2" or key == "TPE1":
            val = traktor_string(value)
        elif key == "FMOD" or key == "RLDT" or key == "IPDT" or key == "FMOD":
            val = struct.pack("<b b H", *[int(a) for a in value.split("/")])
        else:
            val = struct.pack("<"+str(len(value))+"B", *[int(v) for v in value]);
        return struct.pack("<cccc L L", key[3], key[2], key[1], key[0], len(val), 0) + val

filename = "bonus.mp3" or sys.argv[2]

if not(os.path.exists(filename)):
    print "No such file ", filename;
    exit(1);


def findCRC():
    a = eyeD3.Tag()
    a.link(filename);
    data = a.frames[1].data[9:]

    t = {}
    decode(t, 0 , 0 , data)

    chks = t['TRMD'][' HDR']['CHKS']
    chks = int("".join([padhex(a) for a in chks]), 16)

    print "Checking against:\n", chks, "(", hex(chks), ")"
    print "Checking against ", len(data)**2, "possibilities."
    total = 0
    for start in xrange(0, len(data)):
        for end in xrange(0, len(data)):
            start = len(data) - start
            end = len(data) - end
            if not len(data[start:end]):
                pass
            else:
                crc3 = crc32(data[start:end]) & 0xffffffff
                crc1 = crc16.crc16xmodem(data[start:end])

                total += 1
                if crc3 == chks:
                    print "\nFound CRC32 match! data[", start, ":", end, "]"
                    exit(0);
                elif crc1 == chks:
                    print "\nFound CRC16 match! data[", start, ":", end, "]"
                    exit(0);
                elif not total % 50000:
                    print "CRC32 at: ", total, "which is", float(float(total)*100/float((len(data)**2))), "%"
                    print "Datalength: ", len(data[start:end]), "CRC32:", hex(crc3)


def test():
    a = eyeD3.Tag()
    a.link(filename);
    data = a.frames[11].data[9:]

    t = {}
    decode(t, 0 , 0 , data)

    newcue = t['TRMD']['DATA']['CUEP'][6].copy()
    newcue['hotcue'] = 7
    newcue['name'] = "Pork"
    newcue['start'] += 1000
    t['TRMD']['DATA']['CUEP'].append(newcue)

    encoding = encode(t.keys()[0], t.values()[0])
    a.frames[11].data = "TRAKTOR4\x00" + encoding
    a.update()

a = eyeD3.Tag()
a.link(filename);
print a.frames

findCRC()
