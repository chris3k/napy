#!/usr/bin/env python2.7
#-*- coding: utf-8 -*-

#
#     Copyright:
#     This file is part of napy.
#     Copyright (C) 2014 chris3k
#  
#     napy is free software; you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation; either version 2 of the License, or
#     (at your option) any later version.
#  
#     napy is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.
#  
#     You should have received a copy of the GNU General Public License
#     along with napy; if not, see http://www.gnu.org/licenses/
#

import os
import sys

import rarfile
import zipfile

import md5
import urllib, base64
# import StringIO
from xml.dom import minidom

rarfile.NEED_COMMENTS = 0

class Subtitles:
    '''Class contain data required for querying NapiProject for subtitles'''
    
    def __init__(self, f, md5 = None):
        
        self.subtitles_save_path = f
        self.md5sum = md5

class Filesys:
    def __init__(self, paths):
        self.to_process = []

        for f in paths:
            
            absolute_f = os.path.realpath(os.path.join(os.curdir, f))
            print absolute_f
            
            if os.path.isfile(absolute_f):
                if rarfile.is_rarfile(absolute_f):
                    # rar file
                    rarf = rarfile.RarFile(absolute_f)
                    video_list = filter(lambda x: ".mkv" or ".avi" or ".mp4" in x, rarf.namelist())

                    for video_item in video_list:
                        partrarf = rarf.open(video_item)
                        md5hash = self.calculatemd5(partrarf.read(10485760))
                        print "  [rar]md5:", md5hash
                        self.to_process.append(Subtitles( os.path.splitext(os.path.dirname(absolute_f) + os.sep + video_item)[0] + ".txt", md5hash))

                elif zipfile.is_zipfile(absolute_f):
                    # zip file
                    raise NotImplemented("Zip file handle is not implemented yet.")

                else:
                    # raw file
                    if filter(lambda x: ".mkv" or ".avi" or ".mp4" in x, absolute_f):
                        md5hash = self.calculatemd5(open(absolute_f, "rb").read(10485760))
                        print "  [raw]md5:", md5hash
                        self.to_process.append(Subtitles( os.path.splitext(absolute_f)[0] + ".txt", md5hash ))

            elif os.path.isdir(absolute_f):
                # directory
                raise NotImplemented("Directory handle is not implemented yet.")
            
            # get subtitles
            for subtitle_item in self.to_process:
                napi = NapiProjekt(subtitle_item.subtitles_save_path, subtitle_item.md5sum)
                if napi.downloadSubtitles(False):
                    print "    + Pobrano napisy"
                    napi.getMoreInfo()
                else:
                    print "    - NIE POBRANO NAPISOW"
                for k,v in napi.info.iteritems():
                    print "     ", k, ":", v
            
            self.to_process = []
    
    def calculatemd5(self, data):
        if len(data) > 10*1024*1024:
            raise ValueError("Invalid data size (bigger than 10MiB")
        md5sum = md5.new()
        md5sum.update(data)
        md5hash = md5sum.hexdigest()
        return md5hash

class NapiProjekt(object):
    '''Modified class from https://github.com/Miziak/NapiTux/blob/master/NapiProjekt.py'''

    def __init__(self, filename, md5):
        self.info = {}
        self.name = filename
        self.url = "http://napiprojekt.pl/api/api-napiprojekt3.php"
        self.md5hash = md5

    def downloadSubtitles(self, eng = False):
        values = {
            "mode":                      "1",
            "client":                    "NapiProjektPython",
            "client_ver":                "0.1",
            "downloaded_subtitles_id":   self.md5hash,
            "downloaded_subtitles_txt":  "1",
            "downloaded_subtitles_lang": "PL"
        }
        
        if eng:
            values["downloaded_subtitles_lang"] = "ENG"
        
        data = urllib.urlencode(values)
        try:
            response = urllib.urlopen(self.url, data)
        except IOError, e:
            sys.stderr.write("ERROR:" + e.message)
            return False

        try:
            DOMTree = minidom.parseString(response.read())
            
            cNodes = DOMTree.childNodes
            if cNodes[0].getElementsByTagName("status") != []:
                _subtitles = base64.b64decode(cNodes[0].getElementsByTagName("subtitles")[0].getElementsByTagName("content")[0].childNodes[0].data)
#                 with open(os.path.splitext(self.name)[0] + ".txt", "w") as subtitlesfile:
                with open(self.name, "w") as subtitlesfile:
#                     print "[i] saving file to", self.name
                    subtitlesfile.write(_subtitles)
                return True
        except Exception, e:
            sys.stderr.write("ERROR:" + e.message)
            return False
        
        return False

    def getMoreInfo(self):
        values = {
            "mode":                "32770",
            "client":              "NapiProjektPython",
            "client_ver":          "0.1",
            "downloaded_cover_id": self.md5hash,
            "VideoFileInfoID":     self.md5hash
        }
        
        data = urllib.urlencode(values)
        try:
            response = urllib.urlopen(self.url, data)
        except IOError, e:
            sys.stderr.write("ERROR:" + e.message)
            return False

        try:
            DOMTree = minidom.parseString(response.read())
            cNodes = DOMTree.childNodes[0].getElementsByTagName("movie")
            
            if cNodes[0].getElementsByTagName("status") != []:
                self.info["title"] = cNodes[0].getElementsByTagName("title")[0].childNodes[0].data
                self.info["year"] = cNodes[0].getElementsByTagName("year")[0].childNodes[0].data
                self.info["country"] = cNodes[0].getElementsByTagName("country")[0].getElementsByTagName("pl")[0].childNodes[0].data
                if(cNodes[0].getElementsByTagName("genre")[0].getElementsByTagName("pl")[0].childNodes != []):
                    self.info["genre"] = cNodes[0].getElementsByTagName("genre")[0].getElementsByTagName("pl")[0].childNodes[0].data
                else:
                    self.info["genre"] = ""
                
                self.info["filmweb"] = cNodes[0].getElementsByTagName("direct_links")[0].getElementsByTagName("filmweb_pl")[0].childNodes[0].data
#                 self.info["cover"] = StringIO.StringIO(base64.b64decode(cNodes[0].getElementsByTagName("cover")[0].childNodes[0].data))
                
                cNodes = DOMTree.childNodes[0].getElementsByTagName("file_info")
                
                self.info["size"] = cNodes[0].getElementsByTagName("rozmiar_pliku_z_jednostka")[0].childNodes[0].data
                self.info["duration"] = cNodes[0].getElementsByTagName("czas_trwania_sformatowany")[0].childNodes[0].data
                self.info["resolution"] = cNodes[0].getElementsByTagName("rozdz_X")[0].childNodes[0].data + "x" + cNodes[0].getElementsByTagName("rozdz_Y")[0].childNodes[0].data
        except Exception, e:
            sys.stderr.write("ERROR:" + e.message)
            return False

def _help():
    print "Usage: " + sys.argv[0] + " <mkv|mp4|avi|rar file path> [[<mkv|mp4|avi|rar file path>],...]"

def main():
    if len(sys.argv) < 2:
        _help()
        exit(1)

    fs = Filesys(sys.argv[1:])

if __name__ == '__main__':
    assert 10485760 == 10*1024*1024, "10MiB is not 10*1024*1024"
    main()
