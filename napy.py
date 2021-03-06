#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
#     Copyright:
#     This file is part of napy.
#     Copyright (C) 2014-2019 chris3k
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

import base64
import glob
import hashlib
import os
import struct
import sys
import zipfile
import io
from xml.dom import minidom

import rarfile
import requests

rarfile.NEED_COMMENTS = 0


class Subtitles:
    """Class contain data required for querying NapiProjekt for subtitles"""

    def __init__(self, omf, f, md5=None, opensub=None):
        self.original_movie_file = omf
        self.subtitles_save_path = f
        self.md5sum = md5
        self.opensub_hash = opensub


def filterVideoFiles(iterable):
    return filter(lambda x: os.path.splitext(x)[1] in (".mkv", ".avi", ".mp4"), iterable)


def filterArchiveFiles(iterable):
    return filter(lambda x: os.path.splitext(x)[1] in (".rar",), iterable)

def process_http(url):
    r = requests.head(url)
    file_size = r.headers.get("Content-Length")

    buffer = []
    headers = {"Range": "bytes=0-10485759"}
    r = requests.get(url, headers=headers)
    buffer.append(r.content)

    headers = {"Range": "bytes={}-".format(int(file_size) - 65536)}
    r = requests.get(url, headers=headers)
    buffer.append(r.content)

    return file_size, buffer

def get_subtitles(items):
    for subtitle_item in items:
        print(subtitle_item.md5sum, subtitle_item.original_movie_file)
        napi = NapiProjekt(subtitle_item.subtitles_save_path, subtitle_item.md5sum)
        if napi.downloadSubtitles(False):
            print("    + Pobrano napisy PL")
            napi.getMoreInfo()
        elif napi.downloadSubtitles(True):
            print("    + Pobrano napisy ENG")
            napi.getMoreInfo()
        else:
            print("    - NIE POBRANO NAPISOW")
        for k, v in napi.info.items():
            print("     ", k, ":", v)

        napisy24 = Napisy24(subtitle_item.subtitles_save_path, subtitle_item.opensub_hash)
        if napisy24.downloadSubtitles():
            print("    + Pobrano napisy PL (napisy24)")
        else:
            print("    - NIE POBRANO NAPISOW (napisy24)")


class Filesys:
    def __init__(self, paths):
        self.to_process = []  # list[Subtitles]

        for p in paths:
            if p.startswith("http://") or p.startswith("https://"):
                file_size_, buffer = process_http(p)
                file_size = int(file_size_)
                md5hash = self.calculatemd5(buffer[0])
                opensub_hash = Napisy24.buffer_hash(file_size, buffer)
                movie_name = p.rsplit("/", 1)[1]
                movie_subtitles_name = os.path.splitext(movie_name)[0] + ".txt"
                self.to_process.append(Subtitles(movie_name, movie_subtitles_name, md5hash, opensub_hash))

                get_subtitles(self.to_process)
                self.to_process = []
                break

            for f in glob.iglob(p):
                absolute_f = os.path.realpath(os.path.join(os.curdir, f))
                # print absolute_f

                if os.path.isfile(absolute_f):
                    if rarfile.is_rarfile(absolute_f):
                        # rar file
                        self.to_process.extend(self.processRarFile(absolute_f))

                    elif zipfile.is_zipfile(absolute_f):
                        # zip file
                        raise NotImplementedError("Zip file handle is not implemented yet.")

                    else:
                        # raw file
                        self.to_process.extend(self.processRawFile(absolute_f))

                elif os.path.isdir(absolute_f):
                    # directory
                    for rootdir, dirname, filename in os.walk(absolute_f):
                        rawfiles = filterVideoFiles(filename)
                        for i in rawfiles:
                            print(rootdir + os.sep + i)
                            self.to_process.extend(self.processRawFile(rootdir + os.sep + i))

                        rarfiles = filterArchiveFiles(filename)
                        for i in rarfiles:
                            print(rootdir + os.sep + i)
                            self.to_process.extend(self.processRarFile(rootdir + os.sep + i))

                # get subtitles
                get_subtitles(self.to_process)
                self.to_process = []

    def calculatemd5(self, data):
        if len(data) > 10 * 1024 * 1024:
            raise ValueError("Invalid data size (bigger than 10MiB")
        md5sum = hashlib.new("md5")
        md5sum.update(data)
        md5hash = md5sum.hexdigest()
        return md5hash

    def processRarFile(self, path):
        if not rarfile.is_rarfile(path):
            print(path, "is not a valid rar file")
            return []

        rarf = rarfile.RarFile(path)
        video_list = filterVideoFiles(rarf.namelist())
        files_to_process = []

        for video_item in video_list:
            partrarf = rarf.open(video_item)
            md5hash = self.calculatemd5(partrarf.read(10485760))
            opensub_hash = Napisy24.opensubtitle_hash(partrarf)
            print("  [rar]md5:", md5hash)
            print("  [rar]opensub:", opensub_hash)
            files_to_process.append(Subtitles((os.path.dirname(path) + os.sep + video_item),
                                              os.path.splitext(os.path.dirname(path) + os.sep + video_item)[0] + ".txt",
                                              md5hash, opensub_hash))

        return files_to_process

    def processRawFile(self, path):
        if len(list(filterVideoFiles([path]))) < 1:
            return []

        with open(path, "rb") as fh:
            md5hash = self.calculatemd5(fh.read(10485760))
            opensub_hash = Napisy24.opensubtitle_hash(fh)
            print("  [raw]md5:", md5hash)
            print("  [raw]opensub:", opensub_hash)
            return [Subtitles(path, os.path.splitext(path)[0] + ".txt", md5hash, opensub_hash)]


class Napisy24(object):
    def __init__(self, filename, opensub_hash):
        self.name = filename
        self.file_hash = opensub_hash

    @staticmethod
    def file_size(fh):
        fh.seek(0, os.SEEK_END)
        filesize = fh.tell()
        # filesize = os.path.getsize(fh)
        fh.seek(0, os.SEEK_SET)
        return filesize

    @staticmethod
    def opensubtitle_hash(fh):
        """
        :param file fh: file handler to opened file
        :return:
        """
        filesize = Napisy24.file_size(fh)
        if filesize < 65536 * 2:
            raise "SizeError"

        buffer = []
        fh.seek(0, os.SEEK_SET)
        buffer.append(fh.read(65536))

        fh.seek(max(0, filesize - 65536), os.SEEK_SET)
        buffer.append(fh.read(65536))

        assert len(buffer[0]) == 65536, "buffer[0] is " + str(len(buffer[0]))
        assert len(buffer[1]) == 65536, "buffer[1] is " + str(len(buffer[1]))

        opensubs_hash = Napisy24.buffer_hash(filesize, buffer)
        return opensubs_hash, filesize

    @staticmethod
    def buffer_hash(file_size, buffer):
        longlongformat = '<q'  # little-endian long long
        bytesize = struct.calcsize(longlongformat)
        hash_value = file_size
        for x in range(65536 // bytesize):
            buf = buffer[0][x*8:(x+1)*8]
            (l_value,) = struct.unpack(longlongformat, buf)
            hash_value += l_value
            hash_value = hash_value & 0xFFFFFFFFFFFFFFFF  # to remain as 64bit number

        for x in range(65536 // bytesize):
            buf = buffer[1][x*8:(x+1)*8]
            (l_value,) = struct.unpack(longlongformat, buf)
            hash_value += l_value
            hash_value = hash_value & 0xFFFFFFFFFFFFFFFF

        hash_value = "%016x" % hash_value
        return hash_value

    def downloadSubtitles(self):
        # credentials from https://github.com/QNapi/qnapi
        username = "tantalosus"
        password = "susolatnat"

        creds = {"postAction": "CheckSub", "ua": username, "ap": password, "fh": self.file_hash[0],
                 "fs": self.file_hash[1], "fn": self.name}

        r = requests.post("http://napisy24.pl/run/CheckSubAgent.php", data=creds)
        content = r.content
        if not content.startswith(b"OK-2"):
            return False

        split_point = content.find(b"||")
        if split_point == -1:
            return False

        info, subtitles_zip = content[:split_point], content[split_point + len("||"):]
        # print(info)

        # "srt", "sub", "txt"
        szf = io.BytesIO(subtitles_zip)
        with zipfile.ZipFile(szf, "r") as zf:
            subtitles = filter(lambda x: os.path.splitext(x.filename)[1] in (".srt", ".sub", ".txt"), zf.infolist())
            for i in subtitles:
                file_name, file_ext = os.path.splitext(i.filename)
                with open(self.name + "_n24" + file_ext, "wb") as fw:
                    fw.write(zf.read(i))
        return True


class NapiProjekt(object):
    """Modified class from https://github.com/Miziak/NapiTux/blob/master/NapiProjekt.py"""

    def __init__(self, filename, md5):
        self.info = {}
        self.name = filename
        self.url = "http://napiprojekt.pl/api/api-napiprojekt3.php"
        self.file_hash = md5

    def downloadSubtitles(self, eng=False):
        values = {
            "mode": "1",
            "client": "NapiProjektPython",
            "client_ver": "0.1",
            "downloaded_subtitles_id": self.file_hash,
            "downloaded_subtitles_txt": "1",
            "downloaded_subtitles_lang": "PL"
        }

        if eng:
            values["downloaded_subtitles_lang"] = "ENG"

        r = requests.post(self.url, data=values)
        if r.status_code != requests.codes.ok:
            sys.stderr.write("{} error={}\n".format(self.url, r.status_code))
            return False
        response = r.text
        # print(response)

        try:
            DOMTree = minidom.parseString(response)
            cNodes = DOMTree.childNodes
            if cNodes[0].getElementsByTagName("status") != []:
                _subtitles = base64.b64decode(
                    cNodes[0].getElementsByTagName("subtitles")[0].getElementsByTagName("content")[0].childNodes[
                        0].data)
                with open(self.name, "wb") as subtitlesfile:
                    subtitlesfile.write(_subtitles)
                return True
        except Exception as e:
            sys.stderr.write("ERROR: %s\n" % e)
            return False

        return False

    def getMoreInfo(self):
        values = {
            "mode": "32770",
            "client": "NapiProjektPython",
            "client_ver": "0.1",
            "downloaded_cover_id": self.file_hash,
            "VideoFileInfoID": self.file_hash
        }

        r = requests.post(self.url, data=values)
        if r.status_code != requests.codes.ok:
            sys.stderr.write("ERROR: Cannot GET %s\n" % self.url)
            return False
        response = r.text
        # print(response)
        # return

        try:
            DOMTree = minidom.parseString(response)
            cNodes = DOMTree.childNodes[0].getElementsByTagName("movie")

            if cNodes[0].getElementsByTagName("status") != []:
                self.info["title"] = cNodes[0].getElementsByTagName("title")[0].childNodes[0].data
                self.info["year"] = cNodes[0].getElementsByTagName("year")[0].childNodes[0].data
                self.info["country"] = \
                    cNodes[0].getElementsByTagName("country")[0].getElementsByTagName("pl")[0].childNodes[0].data
                if (cNodes[0].getElementsByTagName("genre")[0].getElementsByTagName("pl")[0].childNodes != []):
                    self.info["genre"] = \
                        cNodes[0].getElementsByTagName("genre")[0].getElementsByTagName("pl")[0].childNodes[0].data
                else:
                    self.info["genre"] = ""

                self.info["filmweb"] = \
                    cNodes[0].getElementsByTagName("direct_links")[0].getElementsByTagName("filmweb_pl")[0].childNodes[
                        0].data

                cNodes = DOMTree.childNodes[0].getElementsByTagName("file_info")

                self.info["size"] = cNodes[0].getElementsByTagName("rozmiar_pliku_z_jednostka")[0].childNodes[0].data
                self.info["duration"] = cNodes[0].getElementsByTagName("czas_trwania_sformatowany")[0].childNodes[
                    0].data
                self.info["resolution"] = cNodes[0].getElementsByTagName("rozdz_X")[0].childNodes[0].data + "x" + \
                                          cNodes[0].getElementsByTagName("rozdz_Y")[0].childNodes[0].data
                self.info["fps"] = cNodes[0].getElementsByTagName("fps")[0].childNodes[0].data
        except Exception as e:
            print(self.info)
            sys.stderr.write("ERROR: %s\n" % e)
            return False


def _help():
    print("Usage: " + sys.argv[0] + " <mkv|mp4|avi|rar file path> [[<mkv|mp4|avi|rar file path>],...]")


def main():
    if len(sys.argv) < 2:
        _help()
        exit(1)

    fs = Filesys(sys.argv[1:])


if __name__ == '__main__':
    assert 10485760 == 10 * 1024 * 1024, "10MiB is not 10*1024*1024"
    main()
