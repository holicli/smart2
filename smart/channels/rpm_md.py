#
# Copyright (c) 2004 Conectiva, Inc.
#
# Written by Gustavo Niemeyer <niemeyer@conectiva.com>
#
# This file is part of Smart Package Manager.
#
# Smart Package Manager is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as published
# by the Free Software Foundation; either version 2 of the License, or (at
# your option) any later version.
#
# Smart Package Manager is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Smart Package Manager; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
from smart.backends.rpm.metadata import RPMMetaDataLoader
from smart.util.filetools import getFileDigest

try:
    from xml.etree import ElementTree
except ImportError:
    try:
        from elementtree import ElementTree
    except ImportError:
        from smart.util.elementtree import ElementTree

from smart.const import SUCCEEDED, FAILED, NEVER, ALWAYS
from smart.channel import PackageChannel, MirrorsChannel
from smart import *
import posixpath
import os

from xml.parsers import expat

NS = "{http://linux.duke.edu/metadata/repo}"
DATA = NS+"data"
LOCATION = NS+"location"
CHECKSUM = NS+"checksum"
OPENCHECKSUM = NS+"open-checksum"

class RPMMetaDataChannel(PackageChannel, MirrorsChannel):

    # It's important for the default to be here so that old pickled
    # instances which don't have these attributes still work fine.
    _mirrors = {}
    _mirrorlist = ""

    def __init__(self, baseurl, mirrorlist=None, *args):
        super(RPMMetaDataChannel, self).__init__(*args)
        self._baseurl = baseurl
        self._mirrorlist = mirrorlist

    def getCacheCompareURLs(self):
        return [posixpath.join(self._baseurl, "repodata/repomd.xml")]

    def getFetchSteps(self):
        return 4

    def loadMirrors(self, mirrorlistfile):
        self._mirrors.clear()

        try:
            file = open(mirrorlistfile, 'r')
        except IOError, e:
            iface.warning(_("Could not load mirror list. Continuing with base URL only."))
            iface.debug(e)

        for line in file:
            if line[0] != "#":
                mirror = line.strip()
                if mirror:
                    if self._baseurl in self._mirrors:
                        if mirror not in self._mirrors[self._baseurl]:
                            self._mirrors[self._baseurl].append(mirror)
                    else:
                        self._mirrors[self._baseurl] = [mirror]

    def loadMetadata(self, metadatafile):
        info = {}

        try:
            root = ElementTree.parse(metadatafile).getroot()
        except expat.error, e:
            raise Error, _("Invalid XML file:\n  %s\n  %s") % \
                          (metadatafile, str(e))

        for node in root.getchildren():
            if node.tag != DATA:
                continue
            type = node.get("type")
            info[type] = {}
            for subnode in node.getchildren():
                if subnode.tag == LOCATION:
                    info[type]["url"] = \
                        posixpath.join(self._baseurl, subnode.get("href"))
                if subnode.tag == CHECKSUM:
                    info[type][subnode.get("type")] = subnode.text
                if subnode.tag == OPENCHECKSUM:
                    info[type]["uncomp_"+subnode.get("type")] = \
                        subnode.text
        
        return info
        
    def getLocalPath(self, fetcher, url):
        from smart.fetcher import FetchItem
        mirror = fetcher.getMirrorSystem().get(url)
        item = FetchItem(fetcher, url, mirror)
        return fetcher.getLocalPath(item)

    def fetch(self, fetcher, progress):
        
        fetcher.reset()

        if self._mirrorlist:
            mirrorlist = self._mirrorlist
            item = fetcher.enqueue(mirrorlist)
            fetcher.run(progress=progress)

            if item.getStatus() is FAILED:
                progress.add(self.getFetchSteps()-1)
                if fetcher.getCaching() is NEVER:
                    iface.warning(_("Could not load mirror list. Continuing with base URL only."))
            else:
                self.loadMirrors(item.getTargetPath())

            fetcher.reset()
        else:
            progress.add(1)

        repomd = posixpath.join(self._baseurl, "repodata/repomd.xml")

        oldinfo = {}
        path = self.getLocalPath(fetcher, repomd)
        if os.path.exists(path):
            try:
                oldinfo = self.loadMetadata(path)
            except Error:
                pass
        
        item = fetcher.enqueue(repomd)
        fetcher.run(progress=progress)

        if item.getStatus() is FAILED:
            progress.add(self.getFetchSteps()-1)
            if fetcher.getCaching() is NEVER:
                lines = [_("Failed acquiring release file for '%s':") % self,
                         u"%s: %s" % (item.getURL(), item.getFailedReason())]
                raise Error, "\n".join(lines)
            return False

        digest = getFileDigest(item.getTargetPath())
        if digest == self._digest:
            progress.add(1)
            return True
        self.removeLoaders()

        info = self.loadMetadata(item.getTargetPath())

        if "primary" not in info:
            raise Error, _("Primary information not found in repository "
                           "metadata for '%s'") % self

        fetcher.reset()
        item = fetcher.enqueue(info["primary"]["url"],
                               md5=info["primary"].get("md5"),
                               uncomp_md5=info["primary"].get("uncomp_md5"),
                               sha=info["primary"].get("sha"),
                               uncomp_sha=info["primary"].get("uncomp_sha"),
                               sha256=info["primary"].get("sha256"),
                               uncomp_sha256=info["primary"].get("uncomp_sha256"),
                               uncomp=True)
        flitem = fetcher.enqueue(info["filelists"]["url"],
                                 md5=info["filelists"].get("md5"),
                                 uncomp_md5=info["filelists"].get("uncomp_md5"),
                                 sha=info["filelists"].get("sha"),
                                 uncomp_sha=info["filelists"].get("uncomp_sha"),
                                 sha256=info["filelists"].get("sha256"),
                                 uncomp_sha256=info["filelists"].get("uncomp_sha256"),
                                 uncomp=True)
        fetcher.run(progress=progress)
 
        if item.getStatus() == SUCCEEDED and flitem.getStatus() == SUCCEEDED:
            localpath = item.getTargetPath()
            filelistspath = flitem.getTargetPath()
            loader = RPMMetaDataLoader(localpath, filelistspath,
                                       self._baseurl)
            loader.setChannel(self)
            self._loaders.append(loader)
        elif (item.getStatus() == SUCCEEDED and
              flitem.getStatus() == FAILED and
              fetcher.getCaching() is ALWAYS):
            iface.warning(_("Failed to download. You must fetch channel "
                            "information to acquire needed filelists.\n"
                            "%s: %s") % (flitem.getURL(),
                            flitem.getFailedReason()))
            return False
        elif fetcher.getCaching() is NEVER:
            if item.getStatus() == FAILED:
                faileditem = item
            else:
                faileditem = flitem
            lines = [_("Failed acquiring information for '%s':") % self,
                       u"%s: %s" % (faileditem.getURL(),
                       faileditem.getFailedReason())]
            raise Error, "\n".join(lines)
        else:
            return False

        uncompressor = fetcher.getUncompressor()

        # delete any old files, if the new ones have new names
        for type in ["primary", "filelists", "other"]:
            if type in oldinfo:
                url = oldinfo[type]["url"]
                if url and info[type]["url"] != oldinfo[type]["url"]:
                    path = self.getLocalPath(fetcher, url)
                    if os.path.exists(path):
                       os.unlink(path)
                    handler = uncompressor.getHandler(path)
                    path = handler.getTargetPath(path)
                    if os.path.exists(path):
                       os.unlink(path)

        self._digest = digest

        return True

def create(alias, data):
    return RPMMetaDataChannel(data["baseurl"],
                              data["mirrorlist"],
                              data["type"],
                              alias,
                              data["name"],
                              data["manual"],
                              data["removable"],
                              data["priority"])

# vim:ts=4:sw=4:et
